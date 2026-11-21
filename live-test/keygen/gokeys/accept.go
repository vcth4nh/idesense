package main

import (
	"bufio"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"unicode/utf8"

	"golang.org/x/tools/go/packages"
)

// renameSuffix makes the new name of a renamed identifier: <name>Zq9.
const renameSuffix = "Zq9"

// maxErrors is the count of errors in one output line.
const maxErrors = 5

type acceptLine struct {
	ID      string   `json:"id"`
	Kind    string   `json:"kind"`
	OK      bool     `json:"ok"`
	Errors  []string `json:"errors"`
	Renamed int      `json:"renamed"`
}

type skipLine struct {
	ID      string `json:"id"`
	Kind    string `json:"kind"`
	OK      *bool  `json:"ok"` // always null
	Skipped string `json:"skipped"`
}

// cmdAccept: gokeys accept. For each id it renames the identifier of the record at the sites
// of renameSet, in a copy of the tree, and loads all packages of the copy (with tests) in each
// configuration. The id is ok when no configuration has a load error or a type error. The
// default renames the whole family; -minimal renames only the coupled family.
func cmdAccept(args []string, stdout, stderr io.Writer) int {
	fl := flag.NewFlagSet("accept", flag.ContinueOnError)
	fl.SetOutput(stderr)
	tree := fl.String("tree", "", "root folder of the module; never written")
	keysPath := fl.String("keys", "", "key file (JSONL)")
	idsArg := fl.String("ids", "", "comma-separated ids, or @file with one id on each line")
	sample := fl.Int("sample", 0, "a stable sample of n ids with an empty external list, spread over the kinds")
	seed := fl.Int64("seed", 0, "the seed of -sample")
	configs := fl.String("configs", "", "comma-separated GOOS values; GOARCH is amd64")
	scratch := fl.String("scratch", "", "folder for the copies, one folder for each id")
	keep := fl.Bool("keep", false, "keep the copy of each id")
	minimal := fl.Bool("minimal", false, "rename only the declarations of the coupled family and the uses of its members")
	if err := fl.Parse(args); err != nil {
		return 2
	}
	set := map[string]bool{}
	fl.Visit(func(f *flag.Flag) { set[f.Name] = true })
	goos := splitList(*configs)
	if *tree == "" || *keysPath == "" || *scratch == "" || len(goos) == 0 || fl.NArg() != 0 ||
		(*idsArg != "") == set["sample"] || (set["sample"] && *sample <= 0) || (set["seed"] && !set["sample"]) {
		fmt.Fprintln(stderr, usage)
		return 2
	}
	fail := func(err error) int {
		fmt.Fprintln(stderr, "gokeys accept:", err)
		return 1
	}
	seen := map[string]bool{}
	for _, c := range goos {
		if seen[c] {
			return fail(fmt.Errorf("configuration %s two times", c))
		}
		seen[c] = true
	}
	recs, err := readKeys(*keysPath)
	if err != nil {
		return fail(err)
	}
	byID := map[string]*Record{}
	for i := range recs {
		byID[recs[i].ID] = &recs[i]
	}
	var ids []string
	if *idsArg != "" {
		if ids, err = parseIDs(*idsArg); err != nil {
			return fail(err)
		}
		var unknown []string
		for _, id := range ids {
			if byID[id] == nil {
				unknown = append(unknown, id)
			}
		}
		if len(unknown) > 0 {
			return fail(fmt.Errorf("no record for %s", strings.Join(unknown, ", ")))
		}
	} else {
		ids = sampleIDs(recs, *sample, *seed)
	}
	treeAbs, scratchAbs, err := acceptPaths(*tree, *scratch)
	if err != nil {
		return fail(err)
	}
	files, from, err := treeFiles(treeAbs)
	if err != nil {
		return fail(err)
	}
	mode := "full"
	if *minimal {
		mode = "minimal"
	}
	fmt.Fprintf(stderr, "accept: %d ids, %d files of the tree (%s), configurations %s, %s rename\n", len(ids), len(files), from, strings.Join(goos, ","), mode)

	enc := json.NewEncoder(stdout)
	enc.SetEscapeHTML(false)
	var ok, failed, skipped int
	for _, id := range ids {
		r := byID[id]
		if len(r.External) > 0 {
			skipped++
			if err := enc.Encode(skipLine{ID: id, Kind: r.Kind, Skipped: "external"}); err != nil {
				return fail(err)
			}
			continue
		}
		var line acceptLine
		if sites, err := renameSet(r, byID, *minimal); err != nil {
			line = acceptLine{ID: id, Kind: r.Kind, Errors: []string{err.Error()}}
		} else {
			dir := filepath.Join(scratchAbs, scratchName(id))
			line = acceptOne(r, sites, treeAbs, files, dir, goos)
			if !*keep {
				if err := os.RemoveAll(dir); err != nil {
					return fail(err)
				}
			}
		}
		if line.OK {
			ok++
		} else {
			failed++
		}
		if err := enc.Encode(line); err != nil {
			return fail(err)
		}
	}
	fmt.Fprintf(stderr, "accept: ok %d, failed %d, skipped %d\n", ok, failed, skipped)
	if failed > 0 {
		return 1
	}
	return 0
}

func splitList(s string) []string {
	var out []string
	for _, c := range strings.Split(s, ",") {
		if c = strings.TrimSpace(c); c != "" {
			out = append(out, c)
		}
	}
	return out
}

// readKeys reads the records of a key file, one JSON object for each line.
func readKeys(path string) ([]Record, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	dec := json.NewDecoder(bufio.NewReader(f))
	var recs []Record
	seen := map[string]bool{}
	for {
		var r Record
		if err := dec.Decode(&r); err == io.EOF {
			break
		} else if err != nil {
			return nil, fmt.Errorf("%s: record %d: %w", path, len(recs)+1, err)
		}
		if seen[r.ID] {
			return nil, fmt.Errorf("%s: id %s two times", path, r.ID)
		}
		seen[r.ID] = true
		recs = append(recs, r)
	}
	return recs, nil
}

// parseIDs reads -ids: a comma-separated list, or @file with one id on each line. Empty
// entries are ignored, and an id that comes again is dropped.
func parseIDs(arg string) ([]string, error) {
	var parts []string
	if name, ok := strings.CutPrefix(arg, "@"); ok {
		b, err := os.ReadFile(name)
		if err != nil {
			return nil, err
		}
		parts = strings.Split(string(b), "\n")
	} else {
		parts = strings.Split(arg, ",")
	}
	var ids []string
	seen := map[string]bool{}
	for _, p := range parts {
		if p = strings.TrimSpace(p); p != "" && !seen[p] {
			seen[p] = true
			ids = append(ids, p)
		}
	}
	if len(ids) == 0 {
		return nil, fmt.Errorf("-ids gives no id")
	}
	return ids, nil
}

// sampleIDs gives n ids of the records with an empty external list. In each kind, the ids
// are in the order of sha256("<seed>\x00<id>"); the result takes one id of each kind in turn
// (kinds sorted by name) until it has n ids or no id is left. The order of the key file and
// the other records do not change the rank of an id.
func sampleIDs(recs []Record, n int, seed int64) []string {
	byKind := map[string][]string{}
	rank := map[string]string{}
	for _, r := range recs {
		if len(r.External) != 0 {
			continue
		}
		byKind[r.Kind] = append(byKind[r.Kind], r.ID)
		sum := sha256.Sum256([]byte(fmt.Sprintf("%d\x00%s", seed, r.ID)))
		rank[r.ID] = hex.EncodeToString(sum[:])
	}
	kinds := make([]string, 0, len(byKind))
	for k, list := range byKind {
		kinds = append(kinds, k)
		sort.Slice(list, func(a, b int) bool {
			if rank[list[a]] != rank[list[b]] {
				return rank[list[a]] < rank[list[b]]
			}
			return list[a] < list[b]
		})
	}
	sort.Strings(kinds)
	var out []string
	for i := 0; len(out) < n; i++ {
		more := false
		for _, k := range kinds {
			if i < len(byKind[k]) && len(out) < n {
				out = append(out, byKind[k][i])
				more = true
			}
		}
		if !more {
			break
		}
	}
	return out
}

// within reports whether path is root or below root.
func within(path, root string) bool {
	rel, err := filepath.Rel(root, path)
	return err == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)) && !filepath.IsAbs(rel)
}

// acceptPaths gives the absolute tree and scratch folders, with symbolic links resolved. It
// makes the scratch folder, and refuses a scratch folder in the tree or a tree in the
// scratch folder.
func acceptPaths(tree, scratch string) (string, string, error) {
	treeAbs, err := filepath.Abs(tree)
	if err != nil {
		return "", "", err
	}
	scratchAbs, err := filepath.Abs(scratch)
	if err != nil {
		return "", "", err
	}
	check := func(t, s string) error {
		if within(s, t) || within(t, s) {
			return fmt.Errorf("the scratch folder %s and the tree %s must not contain each other", s, t)
		}
		return nil
	}
	if err := check(treeAbs, scratchAbs); err != nil {
		return "", "", err
	}
	if info, err := os.Stat(treeAbs); err != nil {
		return "", "", err
	} else if !info.IsDir() {
		return "", "", fmt.Errorf("%s is no folder", treeAbs)
	}
	if err := os.MkdirAll(scratchAbs, 0o755); err != nil {
		return "", "", err
	}
	treeReal, err := filepath.EvalSymlinks(treeAbs)
	if err != nil {
		return "", "", err
	}
	scratchReal, err := filepath.EvalSymlinks(scratchAbs)
	if err != nil {
		return "", "", err
	}
	if err := check(treeReal, scratchReal); err != nil {
		return "", "", err
	}
	return treeAbs, scratchReal, nil
}

// skipDirs are the folders that the walk of a tree with no manifest does not copy.
var skipDirs = map[string]bool{".git": true, ".idea": true, ".venv": true}

// treeFiles lists the files of the tree to copy (relative, with forward slashes): the paths
// of <tree>.manifest when it exists, else each file below the tree except in skipDirs.
// from names the source of the list.
func treeFiles(tree string) (files []string, from string, err error) {
	manifest := filepath.Clean(tree) + ".manifest"
	b, err := os.ReadFile(manifest)
	if err == nil {
		for i, line := range strings.Split(strings.TrimSuffix(string(b), "\n"), "\n") {
			_, rel, ok := strings.Cut(line, "  ")
			if !ok || !filepath.IsLocal(filepath.FromSlash(rel)) {
				return nil, "", fmt.Errorf("%s:%d: no line <sha256>  <relative path>", manifest, i+1)
			}
			files = append(files, rel)
		}
		return files, manifest, nil
	}
	if !errors.Is(err, fs.ErrNotExist) {
		return nil, "", err
	}
	err = filepath.WalkDir(tree, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			if path != tree && skipDirs[d.Name()] {
				return filepath.SkipDir
			}
			return nil
		}
		if !d.Type().IsRegular() && d.Type()&fs.ModeSymlink == 0 {
			return nil
		}
		rel, err := filepath.Rel(tree, path)
		if err != nil {
			return err
		}
		files = append(files, filepath.ToSlash(rel))
		return nil
	})
	sort.Strings(files)
	return files, "walk", err
}

// realPath reports whether path names itself with no symbolic link on the way (the folder of
// a copy is a resolved path).
func realPath(path string) bool {
	real, err := filepath.EvalSymlinks(path)
	return err == nil && real == path
}

// copyFiles copies the files (relative to src) to the new folder dst, with their modes; a
// symbolic link stays a link.
func copyFiles(src, dst string, files []string) error {
	if err := os.Mkdir(dst, 0o755); err != nil {
		return err
	}
	for _, rel := range files {
		s := filepath.Join(src, filepath.FromSlash(rel))
		d := filepath.Join(dst, filepath.FromSlash(rel))
		dir := filepath.Dir(d)
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return err
		}
		if !realPath(dir) {
			return fmt.Errorf("%s: a folder of the path is a symbolic link", rel)
		}
		info, err := os.Lstat(s)
		if err != nil {
			return err
		}
		switch {
		case info.Mode()&fs.ModeSymlink != 0:
			target, err := os.Readlink(s)
			if err != nil {
				return err
			}
			if err := os.Symlink(target, d); err != nil {
				return err
			}
		case info.Mode().IsRegular():
			if err := copyFile(s, d, info.Mode().Perm()); err != nil {
				return err
			}
		default:
			return fmt.Errorf("%s: no regular file", rel)
		}
	}
	return nil
}

func copyFile(src, dst string, perm fs.FileMode) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.OpenFile(dst, os.O_WRONLY|os.O_CREATE|os.O_EXCL, perm)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		out.Close()
		return err
	}
	return out.Close()
}

// scratchName gives the folder name of an id: the id with each character other than a
// letter, a digit, ".", "-" and "_" replaced by "_" (at most 120 bytes), and 8 hex digits of
// its hash.
func scratchName(id string) string {
	b := []byte(id)
	for i, c := range b {
		ok := c == '.' || c == '-' || c == '_' || ('0' <= c && c <= '9') || ('a' <= c && c <= 'z') || ('A' <= c && c <= 'Z')
		if !ok {
			b[i] = '_'
		}
	}
	if len(b) > 120 {
		b = b[:120]
	}
	sum := sha256.Sum256([]byte(id))
	return string(b) + "-" + hex.EncodeToString(sum[:4])
}

// renameSet gives the sites to rename for r. The full rename: each site with why "decl" and
// each site with a rel. The minimal rename (-minimal): the declarations of the members of
// coupled, and each site with a rel and no optional flag (the required uses, and the uses in
// a generated file of a coupled member). A function or a type has no coupled list: its
// family is itself. A method or an interface method with no coupled list (a key of an older
// extractor) is an error. When coupled is the whole family, the minimal rename is the full
// rename. Else each declaration site must be the decl of a family record of byID, and the
// record tells the member.
func renameSet(r *Record, byID map[string]*Record, minimal bool) ([]Site, error) {
	var out []Site
	if !minimal {
		for _, s := range r.Sites {
			if s.Why == "decl" || s.Rel != "" {
				out = append(out, s)
			}
		}
		return out, nil
	}
	coupled := r.Coupled
	if coupled == nil {
		if r.Kind == "method" || r.Kind == "iface_method" {
			return nil, fmt.Errorf("the record has no coupled list")
		}
		coupled = r.Family
	}
	fam := map[string]bool{}
	for _, id := range r.Family {
		fam[id] = true
	}
	in := map[string]bool{}
	for _, id := range coupled {
		if !fam[id] {
			return nil, fmt.Errorf("the coupled member %s is not in the family", id)
		}
		in[id] = true
	}
	whole := len(in) == len(fam)
	owner := map[Pos]string{}
	if !whole {
		for _, id := range r.Family {
			m := byID[id]
			if m == nil {
				return nil, fmt.Errorf("the key file has no record of the family member %s", id)
			}
			owner[m.Decl] = id
		}
	}
	for _, s := range r.Sites {
		switch {
		case s.Why == "decl" && whole:
			out = append(out, s)
		case s.Why == "decl":
			id, ok := owner[Pos{s.File, s.Line, s.Col}]
			if !ok {
				return nil, fmt.Errorf("site %s:%d:%d: the declaration is the decl of no family record", s.File, s.Line, s.Col)
			}
			if in[id] {
				out = append(out, s)
			}
		case s.Rel != "" && !s.Optional:
			out = append(out, s)
		}
	}
	return out, nil
}

// acceptOne copies the tree to dir, renames the sites of r and loads each configuration.
func acceptOne(r *Record, sites []Site, tree string, files []string, dir string, configs []string) acceptLine {
	line := acceptLine{ID: r.ID, Kind: r.Kind, Errors: []string{}}
	if err := os.RemoveAll(dir); err != nil {
		line.Errors = []string{"scratch: " + err.Error()}
		return line
	}
	if err := copyFiles(tree, dir, files); err != nil {
		line.Errors = []string{"copy: " + err.Error()}
		return line
	}
	n, errs := renameSites(dir, r.Name, sites)
	if len(errs) == 0 {
		for _, c := range configs {
			for _, e := range loadErrors(dir, c) {
				errs = append(errs, c+": "+e)
			}
		}
	} else {
		n = 0
	}
	line.OK = len(errs) == 0
	line.Renamed = n
	if len(errs) > maxErrors {
		errs = errs[:maxErrors]
	}
	if errs != nil {
		line.Errors = errs
	}
	return line
}

type renameSite struct {
	file      string
	line, col int
	off       int
}

func (s renameSite) String() string { return fmt.Sprintf("%s:%d:%d", s.file, s.line, s.col) }

// renameSites renames the identifier ident to <ident>Zq9 at each site of list (see
// renameSet); two sites at one position count one time. Before it writes a file, it checks
// each site: the text at the site must be ident, as a whole identifier. With an error at any
// site it writes no file and returns the errors.
func renameSites(root, ident string, list []Site) (int, []string) {
	byFile := map[string][]renameSite{}
	seen := map[renameSite]bool{}
	decls := 0
	for _, s := range list {
		if s.Why == "decl" {
			decls++
		}
		rs := renameSite{file: s.File, line: s.Line, col: s.Col}
		if !seen[rs] {
			seen[rs] = true
			byFile[s.File] = append(byFile[s.File], rs)
		}
	}
	if decls == 0 {
		return 0, []string{"the record has no site with why decl"}
	}
	fileNames := make([]string, 0, len(byFile))
	for f := range byFile {
		fileNames = append(fileNames, f)
	}
	sort.Strings(fileNames)

	name := []byte(ident)
	var errs []string
	type edit struct {
		path  string
		perm  fs.FileMode
		src   []byte
		sites []renameSite
	}
	var edits []edit
	for _, f := range fileNames {
		sites := byFile[f]
		sort.Slice(sites, func(a, b int) bool {
			if sites[a].line != sites[b].line {
				return sites[a].line < sites[b].line
			}
			return sites[a].col < sites[b].col
		})
		path := filepath.Join(root, filepath.FromSlash(f))
		var src []byte
		var perm fs.FileMode
		info, err := os.Lstat(path)
		switch {
		case !filepath.IsLocal(filepath.FromSlash(f)):
			err = fmt.Errorf("the path is not relative to the tree root")
		case errors.Is(err, fs.ErrNotExist):
			err = fmt.Errorf("the file is not in the copy of the tree")
		case err != nil:
		case !info.Mode().IsRegular() || !realPath(path):
			err = fmt.Errorf("the file is a symbolic link or below one")
		default:
			perm = info.Mode().Perm()
			src, err = os.ReadFile(path)
		}
		if err != nil {
			errs = append(errs, fmt.Sprintf("site %s: %v", sites[0], err))
			continue
		}
		starts := lineStarts(src)
		for i := range sites {
			off, err := siteOffset(src, starts, sites[i].line, sites[i].col, name)
			if err != nil {
				errs = append(errs, fmt.Sprintf("site %s: %v", sites[i], err))
				continue
			}
			sites[i].off = off
		}
		edits = append(edits, edit{path, perm, src, sites})
	}
	if len(errs) > 0 {
		return 0, errs
	}
	n := 0
	for _, e := range edits {
		out := e.src
		// From the end of the file to its start: an edit does not move the earlier offsets.
		for i := len(e.sites) - 1; i >= 0; i-- {
			off := e.sites[i].off
			end := off + len(name)
			out = append(out[:end:end], append([]byte(renameSuffix), out[end:]...)...)
			n++
		}
		if err := os.WriteFile(e.path, out, e.perm); err != nil {
			return 0, []string{fmt.Sprintf("site %s: %v", e.sites[0], err)}
		}
	}
	return n, nil
}

// lineStarts gives the byte offset of the start of each line of src (index 0: line 1).
func lineStarts(src []byte) []int {
	starts := []int{0}
	for i, c := range src {
		if c == '\n' {
			starts = append(starts, i+1)
		}
	}
	return starts
}

// siteOffset gives the byte offset of the 1-based line and the 1-based column in UTF-16 code
// units (a character above U+FFFF counts as 2, an invalid UTF-8 byte as 1), and checks that
// the identifier there is name.
func siteOffset(src []byte, starts []int, line, col int, name []byte) (int, error) {
	if line < 1 || line > len(starts) {
		return 0, fmt.Errorf("line %d is not in the file (%d lines)", line, len(starts))
	}
	start := starts[line-1]
	end := len(src)
	if line < len(starts) {
		end = starts[line] - 1
	}
	off, units := start, 1
	for units < col && off < end {
		r, n := utf8.DecodeRune(src[off:end])
		if r > 0xFFFF {
			units += 2
		} else {
			units++
		}
		off += n
	}
	if units < col {
		return 0, fmt.Errorf("column %d is beyond the end of line %d", col, line)
	}
	if col < 1 || units != col {
		return 0, fmt.Errorf("column %d is not the start of a character of line %d", col, line)
	}
	wordEnd := off
	for wordEnd < end {
		r, n := utf8.DecodeRune(src[wordEnd:end])
		if !isIdentRune(r) {
			break
		}
		wordEnd += n
	}
	prev, _ := utf8.DecodeLastRune(src[start:off])
	if (off > start && isIdentRune(prev)) || !bytes.Equal(src[off:wordEnd], name) {
		word := src[off:wordEnd]
		if len(word) == 0 {
			word = src[off:min(off+len(name), end)]
		}
		return 0, fmt.Errorf("the text there is %q, not the name %s", word, name)
	}
	return off, nil
}

// loadErrors loads all packages of the module at dir (with tests) for one GOOS, as the
// extractor does, and returns each load error and type error of the package graph, with
// the paths relative to dir, sorted. GOPROXY=off: the load uses only the module cache.
func loadErrors(dir, goos string) []string {
	cfg := &packages.Config{
		Mode:  loadMode,
		Dir:   dir,
		Tests: true,
		Env:   append(os.Environ(), "GOOS="+goos, "GOARCH=amd64", "GOWORK=off", "GOPROXY=off"),
	}
	initial, err := packages.Load(cfg, "./...")
	if err != nil {
		return []string{"load: " + relPaths(err.Error(), dir)}
	}
	if len(initial) == 0 {
		return []string{"load: no package"}
	}
	seen := map[string]bool{}
	var errs []string
	packages.Visit(initial, nil, func(p *packages.Package) {
		for _, e := range p.Errors {
			s := relPaths(e.Error(), dir)
			if !seen[s] {
				seen[s] = true
				errs = append(errs, s)
			}
		}
	})
	sort.Strings(errs)
	return errs
}

func relPaths(s, dir string) string {
	return strings.ReplaceAll(s, dir+string(filepath.Separator), "")
}
