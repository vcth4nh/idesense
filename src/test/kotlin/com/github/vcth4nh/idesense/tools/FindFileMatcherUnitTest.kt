package com.github.vcth4nh.idesense.tools

import com.github.vcth4nh.idesense.tools.navigation.FindFileTool
import com.intellij.psi.codeStyle.NameUtil
import junit.framework.TestCase

/**
 * Unit tests for FindFileTool's matcher pattern construction (#16).
 *
 * The tool prepends "*" so plain queries match as substrings ("User" → UserService.java).
 * A query that already starts with "*" must not be double-starred: "**.java" degenerates
 * in MinusculeMatcher and stops matching names like "Demo.java" entirely.
 */
class FindFileMatcherUnitTest : TestCase() {

    private fun matches(query: String, name: String): Boolean =
        NameUtil.buildMatcher(FindFileTool.matcherPattern(query), NameUtil.MatchingCaseSensitivity.NONE)
            .matches(name)

    fun testPlainQueryGetsContainsPrefix() {
        assertEquals("*User", FindFileTool.matcherPattern("User"))
    }

    fun testLeadingWildcardIsNotDoubled() {
        assertEquals("*.java", FindFileTool.matcherPattern("*.java"))
        assertEquals("*Test.kt", FindFileTool.matcherPattern("*Test.kt"))
    }

    fun testBareExtensionWildcardMatches() {
        assertTrue(matches("*.java", "Demo.java"))
        assertFalse(matches("*.java", "Demo.kt"))
    }

    fun testSubstringAndWildcardShapesStillMatch() {
        assertTrue(matches("User", "UserService.java"))
        assertTrue(matches("*Test.kt", "MyTest.kt"))
        assertTrue(matches("Super.java", "GenericSuper.java"))
    }

    // Extension-only queries are not end-anchored, so they also admit longer-extension
    // names (".py" ⊂ ".pyi"/".pyc"). Harmless per se, but it is why the candidate-name
    // enumeration must never be truncated: these shapes admit the machine-wide VFS name
    // universe, and a capped collection starved out in-scope files (#87). A trailing space
    // end-anchors the pattern and rejects them — both behaviors mirror the IDE popup.
    fun testBareExtensionQueryAdmitsLongerExtensions() {
        assertTrue(matches("*.py", "builtins.pyi"))
        assertTrue(matches("*.py", "normal.cpython-312.pyc"))
        assertTrue(matches("*.py", "normal.py"))
    }

    fun testTrailingSpaceEndAnchorsExtensionQuery() {
        assertFalse(matches("*.py ", "builtins.pyi"))
        assertFalse(matches("*.py ", "normal.cpython-312.pyc"))
        assertTrue(matches("*.py ", "normal.py"))
    }
}
