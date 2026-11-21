package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"go/scanner"
	"go/token"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"unicode"
	"unicode/utf8"
)

// A word is one occurrence of an identifier-shaped word in a Go source file: an identifier
// token ("code"), or a word in a comment ("comment") or in a string or rune literal
// ("string"). Line and Col are 1-based; Col counts UTF-16 code units, as the IDE plugin
// does, not the bytes of go/token.
type word struct {
	Text string
	Line int
	Col  int
	In   string
}

// scanWords returns the words of src in source order. A word in a comment or a literal is
// a maximal run of letters, digits and underscores, so a name matches it only as a whole
// word. Positions ignore //line directives: they are the positions in the file itself.
func scanWords(src []byte) []word {
	fset := token.NewFileSet()
	file := fset.AddFile("", -1, len(src))
	var s scanner.Scanner
	s.Init(file, src, nil, scanner.ScanComments)
	type span struct {
		start, end int
		in, lit    string
	}
	var spans []span
	for {
		pos, tok, lit := s.Scan()
		if tok == token.EOF {
			break
		}
		off := file.Offset(pos)
		switch tok {
		case token.IDENT:
			spans = append(spans, span{off, off + len(lit), "code", lit})
		case token.COMMENT:
			spans = append(spans, span{off, commentEnd(src, off), "comment", ""})
		case token.STRING, token.CHAR:
			spans = append(spans, span{off, literalEnd(src, off, lit), "string", ""})
		}
	}
	// The line table of file is complete only after the whole source is scanned.
	at := func(off int) (int, int) {
		p := file.PositionFor(file.Pos(off), false)
		return p.Line, charCol(src, p.Offset, p.Column)
	}
	var out []word
	for _, sp := range spans {
		if sp.in == "code" {
			line, col := at(sp.start)
			out = append(out, word{sp.lit, line, col, "code"})
			continue
		}
		text := src[sp.start:sp.end]
		for i := 0; i < len(text); {
			r, n := utf8.DecodeRune(text[i:])
			if !isIdentRune(r) {
				i += n
				continue
			}
			j := i
			for j < len(text) {
				r, n := utf8.DecodeRune(text[j:])
				if !isIdentRune(r) {
					break
				}
				j += n
			}
			line, col := at(sp.start + i)
			out = append(out, word{string(text[i:j]), line, col, sp.in})
			i = j
		}
	}
	return out
}

// charCol converts the 1-based byte column byteCol of the byte offset off in src to the
// 1-based column of the IDE plugin: one more than the count of UTF-16 code units between
// the start of the line and off. A character above U+FFFF counts as 2; an invalid UTF-8
// byte counts as 1.
func charCol(src []byte, off, byteCol int) int {
	col := 1
	for _, r := range string(src[off-(byteCol-1) : off]) {
		if r > 0xFFFF {
			col += 2
		} else {
			col++
		}
	}
	return col
}

func isIdentRune(r rune) bool {
	return r == '_' || unicode.IsLetter(r) || unicode.IsDigit(r)
}

// commentEnd gives the end offset of the comment that starts at off. The scanner removes
// carriage returns from the comment text, so the end comes from the source.
func commentEnd(src []byte, off int) int {
	if off+1 < len(src) && src[off+1] == '/' {
		if i := bytes.IndexByte(src[off:], '\n'); i >= 0 {
			return off + i
		}
		return len(src)
	}
	if i := bytes.Index(src[off+2:], []byte("*/")); i >= 0 {
		return off + 2 + i + 2
	}
	return len(src)
}

// literalEnd gives the end offset of the string or rune literal that starts at off. The
// scanner removes carriage returns from a raw string, so its end comes from the source.
func literalEnd(src []byte, off int, lit string) int {
	if src[off] == '`' {
		if i := bytes.IndexByte(src[off+1:], '`'); i >= 0 {
			return off + 1 + i + 1
		}
		return len(src)
	}
	return off + len(lit)
}

// goFiles lists the .go files below root (relative, with forward slashes, sorted). It skips
// the folders whose name starts with a dot.
func goFiles(root string) ([]string, error) {
	var files []string
	err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			if path != root && strings.HasPrefix(d.Name(), ".") {
				return filepath.SkipDir
			}
			return nil
		}
		if strings.HasSuffix(d.Name(), ".go") {
			rel, err := filepath.Rel(root, path)
			if err != nil {
				return err
			}
			files = append(files, filepath.ToSlash(rel))
		}
		return nil
	})
	sort.Strings(files)
	return files, err
}

type identLine struct {
	File string `json:"file"`
	Line int    `json:"line"`
	Col  int    `json:"col"`
	In   string `json:"in"`
}

// cmdIdents: gokeys idents -tree <dir> -name <identifier>. One JSON line for each
// occurrence of the identifier in each .go file of the tree.
func cmdIdents(args []string, stdout, stderr io.Writer) int {
	fl := flag.NewFlagSet("idents", flag.ContinueOnError)
	fl.SetOutput(stderr)
	tree := fl.String("tree", "", "root folder of the tree")
	name := fl.String("name", "", "the identifier")
	if err := fl.Parse(args); err != nil {
		return 2
	}
	if *tree == "" || *name == "" || fl.NArg() != 0 {
		fmt.Fprintln(stderr, usage)
		return 2
	}
	files, err := goFiles(*tree)
	if err != nil {
		fmt.Fprintln(stderr, "gokeys idents:", err)
		return 1
	}
	enc := json.NewEncoder(stdout)
	enc.SetEscapeHTML(false)
	for _, rel := range files {
		src, err := os.ReadFile(filepath.Join(*tree, filepath.FromSlash(rel)))
		if err != nil {
			fmt.Fprintln(stderr, "gokeys idents:", err)
			return 1
		}
		for _, w := range scanWords(src) {
			if w.Text == *name {
				if err := enc.Encode(identLine{rel, w.Line, w.Col, w.In}); err != nil {
					fmt.Fprintln(stderr, "gokeys idents:", err)
					return 1
				}
			}
		}
	}
	return 0
}
