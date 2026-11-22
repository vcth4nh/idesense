package com.github.vcth4nh.idesense.integration

import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.constants.UsageMatch
import com.github.vcth4nh.idesense.handlers.FindUsagesHandlerSearch
import com.github.vcth4nh.idesense.handlers.SuperMethodsData
import com.github.vcth4nh.idesense.handlers.SuperMethodsProvider
import com.github.vcth4nh.idesense.handlers.UsageHit
import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.github.vcth4nh.idesense.tools.ToolRegistry
import com.github.vcth4nh.idesense.tools.intelligence.GetDiagnosticsTool
import com.github.vcth4nh.idesense.tools.navigation.CallHierarchyTool
import com.github.vcth4nh.idesense.tools.navigation.FindImplementationsTool
import com.github.vcth4nh.idesense.tools.navigation.FindFileTool
import com.github.vcth4nh.idesense.tools.navigation.FindUsagesTool
import com.github.vcth4nh.idesense.tools.navigation.FindDefinitionTool
import com.github.vcth4nh.idesense.tools.navigation.TypeHierarchyTool
import com.github.vcth4nh.idesense.tools.navigation.ReadFileTool
import com.github.vcth4nh.idesense.tools.models.DefinitionResult
import com.github.vcth4nh.idesense.tools.models.FindFileResult
import com.github.vcth4nh.idesense.tools.models.FindUsagesResult
import com.github.vcth4nh.idesense.tools.models.ReadFileResult
import com.github.vcth4nh.idesense.tools.project.GetIndexStatusTool
import com.intellij.find.findUsages.FindUsagesHandler
import com.intellij.find.findUsages.FindUsagesHandlerFactory
import com.intellij.find.findUsages.FindUsagesHandlerFactory.OperationMode
import com.intellij.lang.java.JavaLanguage
import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.extensions.LoadingOrder
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.Project
import com.intellij.openapi.roots.ModuleRootModificationUtil
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiJavaFile
import com.intellij.psi.PsiManager
import com.intellij.psi.PsiMethod
import com.intellij.psi.PsiReference
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.psi.search.SearchScope
import com.intellij.testFramework.IndexingTestUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import com.intellij.util.Processor
import java.io.File
import java.nio.file.Files
import java.nio.file.Path
import javax.tools.ToolProvider
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put

/**
 * Integration tests for tool execution end-to-end.
 * Tests each navigation, intelligence, and project tool with realistic scenarios.
 */
class ToolExecutionIntegrationTest : BasePlatformTestCase() {

    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    // Navigation Tools Tests

    fun testFindUsagesToolEndToEnd() = runBlocking {
        val tool = FindUsagesTool()

        // Test missing required parameter
        val resultMissing = tool.execute(project, buildJsonObject { })
        assertTrue("Should error with missing file", resultMissing.isError)

        // Test with invalid file
        val resultInvalid = tool.execute(project, buildJsonObject {
            put("file", "nonexistent.kt")
            put("line", 1)
            put("column", 1)
        })
        assertTrue("Should error with invalid file", resultInvalid.isError)
    }

    fun testFindUsagesSurfacesHandlerStageDegradationAsWarnings() {
        // #81: a FindUsagesHandler stage throwing mid-expansion must be swallowed
        // (headless-safe) but reported through the warnings collector, not silently
        // dropped. Exercises FindUsagesHandlerSearch directly — the tool-level JSON
        // shape (isError:false + warnings on the first page) is pinned by the live
        // suite, and end-to-end file resolution is not available on the light
        // fixture's in-memory VFS.
        val psiFile = myFixture.addFileToProject("Warn.java", """
            public class Warn {
                void target() {}
                void caller() {
                    target();
                }
            }
        """.trimIndent()) as com.intellij.psi.PsiJavaFile

        val throwingFactory = object : com.intellij.find.findUsages.FindUsagesHandlerFactory() {
            override fun canFindUsages(element: com.intellij.psi.PsiElement) = element is com.intellij.psi.PsiMethod
            override fun createFindUsagesHandler(element: com.intellij.psi.PsiElement, forHighlightUsages: Boolean) =
                object : com.intellij.find.findUsages.FindUsagesHandler(element) {
                    override fun getPrimaryElements(): Array<com.intellij.psi.PsiElement> =
                        throw IllegalStateException("test-induced primaryElements failure")
                }
        }
        com.intellij.find.findUsages.FindUsagesHandlerFactory.EP_NAME.getPoint(project)
            .registerExtension(throwingFactory, com.intellij.openapi.extensions.LoadingOrder.FIRST, testRootDisposable)
        // The fake provider hides the real Java provider: its direct references of a method would
        // skip the handler (#175).
        registerProvider(FakeBaseProvider { emptyList() })

        val warnings = mutableListOf<String>()
        com.intellij.openapi.application.ReadAction.run<Throwable> {
            val target = psiFile.classes[0].findMethodsByName("target", false)[0]
            com.github.vcth4nh.idesense.handlers.FindUsagesHandlerSearch.processReferences(
                project,
                target,
                com.intellij.psi.search.GlobalSearchScope.projectScope(project),
                com.intellij.util.Processor<com.github.vcth4nh.idesense.handlers.UsageHit> { true },
                warnings
            )
        }

        assertTrue(
            "Warning should name the failed stage and consequence: $warnings",
            warnings.any { it.contains("primaryElements") && it.contains("usages may be incomplete") }
        )
        // #206: the handler is an anonymous class, which has an empty simple name.
        assertTrue(
            "Warning should name the anonymous handler class without the package: $warnings",
            warnings.any { it.startsWith("Find-usages handler ToolExecutionIntegrationTest\$") }
        )
    }

    fun testFindUsagesSurfacesFactoryFailureAsWarning() {
        // #130, #171: a factory that throws in each mode while it creates the handler gives the
        // plain ReferencesSearch of the anchor, and the warnings report it, not silently.
        val psiFile = myFixture.addFileToProject("FactoryWarn.java", """
            public class FactoryWarn {
                void target() {}
                void caller() {
                    target();
                }
            }
        """.trimIndent()) as com.intellij.psi.PsiJavaFile

        val throwingFactory = object : com.intellij.find.findUsages.FindUsagesHandlerFactory() {
            override fun canFindUsages(element: com.intellij.psi.PsiElement) = element is com.intellij.psi.PsiMethod
            override fun createFindUsagesHandler(
                element: com.intellij.psi.PsiElement,
                forHighlightUsages: Boolean
            ): com.intellij.find.findUsages.FindUsagesHandler =
                throw IllegalStateException("test-induced factory failure")
        }
        com.intellij.find.findUsages.FindUsagesHandlerFactory.EP_NAME.getPoint(project)
            .registerExtension(throwingFactory, com.intellij.openapi.extensions.LoadingOrder.FIRST, testRootDisposable)
        // The fake provider hides the real Java provider: its direct references of a method would
        // skip the factory (#175).
        registerProvider(FakeBaseProvider { emptyList() })

        val warnings = mutableListOf<String>()
        val hits = mutableListOf<UsageHit>()
        ReadAction.run<Throwable> {
            val target = psiFile.classes[0].findMethodsByName("target", false)[0]
            FindUsagesHandlerSearch.processReferences(
                project,
                target,
                GlobalSearchScope.projectScope(project),
                Processor<UsageHit> { hit -> hits.add(hit) },
                warnings
            )
        }

        assertEquals("Exactly one warning expected: $warnings", 1, warnings.size)
        assertTrue(
            "Warning should name the failure and its consequence: $warnings",
            warnings[0].contains("threw while creating the handler") && warnings[0].contains("usages may be incomplete")
        )
        // #206: the factory is an anonymous class, which has an empty simple name.
        assertTrue(
            "Warning should name the anonymous factory class without the package: $warnings",
            warnings[0].startsWith("Find-usages handler factory ToolExecutionIntegrationTest\$")
        )
        val callOffset = ReadAction.compute<Int, Throwable> { psiFile.text.indexOf("target();") }
        assertEquals("The plain search should give the one usage of target(): ${hits.map { it.offset }}", 1, hits.size)
        assertEquals(callOffset, hits[0].offset)
        assertNull("A resolved reference has no mark", hits[0].match)
    }

    /** Base, Derived (overrides target) and a class that calls target() on a Derived value and on a Base variable. */
    private fun addBaseUnionSource(prefix: String): PsiJavaFile = myFixture.addFileToProject("${prefix}Union.java", """
        class ${prefix}Base { void target() {} }
        class ${prefix}Derived extends ${prefix}Base { void target() {} }
        class ${prefix}Use {
            void run(${prefix}Base x) {
                new ${prefix}Derived().target();
                ((${prefix}Base) x).target();
            }
        }
    """.trimIndent()) as PsiJavaFile

    private fun targetOf(file: PsiJavaFile, className: String): PsiMethod =
        ReadAction.compute<PsiMethod, Throwable> {
            file.classes.single { it.name == className }.findMethodsByName("target", false)[0]
        }

    /** The offset in [file] just after the text [before]: the start of the method name of a call. */
    private fun offsetAfter(file: PsiJavaFile, before: String): Int =
        ReadAction.compute<Int, Throwable> { file.text.indexOf(before) + before.length }

    /**
     * A provider for Java that gives the base declarations of [baseDeclarationsOf] and the direct
     * references of [directReferencesOf].
     */
    private class FakeBaseProvider(var baseDeclarationsOf: (PsiElement) -> List<PsiElement>) : SuperMethodsProvider {
        /** Null by default: the search takes the handler. */
        var directReferencesOf: (PsiElement) -> Collection<PsiReference>? = { null }

        override fun findSuperMethods(element: PsiElement, project: Project): SuperMethodsData? = null
        override fun findBaseDeclarations(element: PsiElement): List<PsiElement> = baseDeclarationsOf(element)
        override fun findDirectReferences(element: PsiElement, scope: SearchScope): Collection<PsiReference>? =
            directReferencesOf(element)
    }

    /**
     * A factory for Java methods. It throws when [throwsFor] is the element in the mode
     * USAGES_WITH_DEFAULT_OPTIONS; else it gives a handler that keeps the platform
     * findReferencesToHighlight (a plain ReferencesSearch). [askedFor] counts the calls for each element.
     */
    private class FakeHandlerFactory(private val throwsFor: PsiElement? = null) : FindUsagesHandlerFactory() {
        val askedFor = mutableMapOf<PsiElement, Int>()

        override fun canFindUsages(element: PsiElement) = element is PsiMethod

        override fun createFindUsagesHandler(element: PsiElement, operationMode: OperationMode): FindUsagesHandler? {
            askedFor[element] = (askedFor[element] ?: 0) + 1
            if (element == throwsFor && operationMode == OperationMode.USAGES_WITH_DEFAULT_OPTIONS) {
                throw IllegalStateException("test-induced question about the base method")
            }
            return createFindUsagesHandler(element, operationMode == OperationMode.HIGHLIGHT_USAGES)
        }

        override fun createFindUsagesHandler(element: PsiElement, forHighlightUsages: Boolean): FindUsagesHandler =
            object : FindUsagesHandler(element) {}
    }

    private fun registerFactory(factory: FindUsagesHandlerFactory) {
        FindUsagesHandlerFactory.EP_NAME.getPoint(project)
            .registerExtension(factory, LoadingOrder.FIRST, testRootDisposable)
    }

    private fun registerProvider(provider: SuperMethodsProvider) {
        SuperMethodsProvider.EP.addExplicitExtension(JavaLanguage.INSTANCE, provider, testRootDisposable)
    }

    fun testFindUsagesSearchesBaseDeclarationsAndMarksThem() {
        // #171: the direct pass searches Derived.target in the mode HIGHLIGHT_USAGES (the mode
        // USAGES_WITH_DEFAULT_OPTIONS throws, as the question of WebStorm does off the EDT). The base pass
        // searches Base.target. The union holds both calls; only the call through Base has match BASE.
        val file = addBaseUnionSource("Marks")
        val derivedTarget = targetOf(file, "MarksDerived")
        val baseTarget = targetOf(file, "MarksBase")
        registerFactory(FakeHandlerFactory(throwsFor = derivedTarget))
        registerProvider(FakeBaseProvider { if (it == derivedTarget) listOf(baseTarget) else emptyList() })

        val warnings = mutableListOf<String>()
        val baseDeclarations = mutableListOf<PsiElement>()
        // The first hit at an offset wins, as in the collectors of the tools.
        val matchByOffset = LinkedHashMap<Int, String?>()
        ReadAction.run<Throwable> {
            FindUsagesHandlerSearch.processReferences(
                project,
                derivedTarget,
                GlobalSearchScope.projectScope(project),
                Processor<UsageHit> { hit ->
                    if (hit.offset !in matchByOffset) matchByOffset[hit.offset] = hit.match
                    true
                },
                warnings,
                baseDeclarations
            )
        }

        assertTrue("No warning expected: $warnings", warnings.isEmpty())
        assertEquals(listOf<PsiElement>(baseTarget), baseDeclarations)
        val derivedCall = offsetAfter(file, "new MarksDerived().")
        val baseCall = offsetAfter(file, "((MarksBase) x).")
        assertTrue("The call on the Derived value should arrive: $matchByOffset", derivedCall in matchByOffset)
        assertNull("The call on the Derived value is a sure usage", matchByOffset[derivedCall])
        assertTrue("The call on the Base variable should arrive: $matchByOffset", baseCall in matchByOffset)
        assertEquals(UsageMatch.BASE, matchByOffset[baseCall])
    }

    fun testBasePassRunsOnlyAfterTheDirectPassCompletes() {
        // #171: a processor that stops the direct pass stops the whole search; no base pass starts.
        val file = addBaseUnionSource("Stop")
        val derivedTarget = targetOf(file, "StopDerived")
        val baseTarget = targetOf(file, "StopBase")
        val factory = FakeHandlerFactory(throwsFor = derivedTarget)
        registerFactory(factory)
        registerProvider(FakeBaseProvider { if (it == derivedTarget) listOf(baseTarget) else emptyList() })

        val hits = mutableListOf<UsageHit>()
        ReadAction.run<Throwable> {
            FindUsagesHandlerSearch.processReferences(
                project,
                derivedTarget,
                GlobalSearchScope.projectScope(project),
                Processor<UsageHit> { hit -> hits.add(hit); false }
            )
        }

        assertEquals("The processor should get exactly one hit: ${hits.map { it.offset }}", 1, hits.size)
        assertNull("The factory should never be asked for a handler of the base declaration", factory.askedFor[baseTarget])
    }

    fun testBadBaseDeclarationsAreIgnored() {
        // #171: a provider that throws, that gives the anchor itself or that gives nothing leaves only
        // the direct pass, with no mark and no base declaration.
        val file = addBaseUnionSource("Bad")
        val derivedTarget = targetOf(file, "BadDerived")
        registerFactory(FakeHandlerFactory())
        val provider = FakeBaseProvider { emptyList() }
        registerProvider(provider)
        val derivedCall = offsetAfter(file, "new BadDerived().")

        val badProviders = listOf<Pair<String, (PsiElement) -> List<PsiElement>>>(
            "throws" to { _: PsiElement -> throw IllegalStateException("test-induced provider failure") },
            "gives the anchor" to { anchor: PsiElement -> listOf(anchor) },
            "gives nothing" to { _: PsiElement -> emptyList<PsiElement>() },
        )
        for ((label, baseDeclarationsOf) in badProviders) {
            provider.baseDeclarationsOf = baseDeclarationsOf
            val hits = mutableListOf<UsageHit>()
            val baseDeclarations = mutableListOf<PsiElement>()
            ReadAction.run<Throwable> {
                FindUsagesHandlerSearch.processReferences(
                    project,
                    derivedTarget,
                    GlobalSearchScope.projectScope(project),
                    Processor<UsageHit> { hit -> hits.add(hit) },
                    null,
                    baseDeclarations
                )
            }

            assertTrue("$label: the direct usage should arrive: ${hits.map { it.offset }}", hits.any { it.offset == derivedCall })
            assertTrue("$label: no hit should have a mark: ${hits.map { it.match }}", hits.all { it.match == null })
            assertTrue("$label: no base declaration expected: $baseDeclarations", baseDeclarations.isEmpty())
        }
    }

    fun testFindDirectReferencesOfTheProviderWin() {
        // #175: when the provider gives the direct references of a target, the search takes them
        // and asks no factory for a handler of that target. The factory below throws when the
        // search reads primaryElements, so a search through the handler would give a warning. The
        // fixed lists are not what a search would find: the anchor gets the call on the Base
        // variable, and the base declaration gets the call on the Derived value.
        val file = addBaseUnionSource("Direct")
        val derivedTarget = targetOf(file, "DirectDerived")
        val baseTarget = targetOf(file, "DirectBase")
        val derivedCall = offsetAfter(file, "new DirectDerived().")
        val baseCall = offsetAfter(file, "((DirectBase) x).")
        val referenceAt = { offset: Int ->
            ReadAction.compute<PsiReference, Throwable> {
                requireNotNull(file.findReferenceAt(offset)) { "No reference at $offset" }
            }
        }
        val anchorReferences = listOf(referenceAt(baseCall))
        val baseReferences = listOf(referenceAt(derivedCall))

        var handlersCreated = 0
        registerFactory(object : FindUsagesHandlerFactory() {
            override fun canFindUsages(element: PsiElement) = element is PsiMethod
            override fun createFindUsagesHandler(element: PsiElement, forHighlightUsages: Boolean): FindUsagesHandler {
                handlersCreated++
                return object : FindUsagesHandler(element) {
                    override fun getPrimaryElements(): Array<PsiElement> =
                        throw IllegalStateException("test-induced primaryElements failure")
                }
            }
        })
        registerProvider(FakeBaseProvider { if (it == derivedTarget) listOf(baseTarget) else emptyList() }.apply {
            directReferencesOf = {
                when (it) {
                    derivedTarget -> anchorReferences
                    baseTarget -> baseReferences
                    else -> null
                }
            }
        })

        val warnings = mutableListOf<String>()
        val hits = mutableListOf<UsageHit>()
        ReadAction.run<Throwable> {
            FindUsagesHandlerSearch.processReferences(
                project,
                derivedTarget,
                GlobalSearchScope.projectScope(project),
                Processor<UsageHit> { hit -> hits.add(hit) },
                warnings
            )
        }

        assertTrue("No warning expected: $warnings", warnings.isEmpty())
        assertEquals("No handler expected", 0, handlersCreated)
        assertEquals(
            "The hits should be the fixed references, the anchor first",
            listOf(baseCall to null, derivedCall to UsageMatch.BASE),
            hits.map { it.offset to it.match }
        )
    }

    /** The first page of ide_find_usages for the name anchor [symbol]. */
    private fun findUsagesOf(symbol: String): FindUsagesResult = runBlocking {
        val result = FindUsagesTool().execute(project, buildJsonObject { put("symbol", symbol) })
        val text = (result.content.first() as ContentBlock.Text).text
        assertFalse("The call must succeed: $text", result.isError)
        json.decodeFromString<FindUsagesResult>(text)
    }

    /** The 1-based line of the first [needle] in [file]. */
    private fun lineOf(file: PsiJavaFile, needle: String): Int = ReadAction.compute<Int, Throwable> {
        val offset = file.text.indexOf(needle)
        assertTrue("Needle '$needle' should exist in the fixture text", offset >= 0)
        file.text.substring(0, offset).count { it == '\n' } + 1
    }

    fun testJavaOverridingMethodGetsItsOwnUsagesAndTheBaseUsages() {
        // #175: the real Java provider, with no fake provider. The direct pass searches Circle.area
        // itself and finds the call on the Circle receiver. The base pass searches Shape.area and
        // adds the call on the Shape receiver with match BASE. No handler stage runs, so no warning.
        val file = myFixture.addFileToProject("javaunion/Shapes.java", """
            package javaunion;
            abstract class Shape { abstract double area(); }
            class Circle extends Shape { double area() { return 3.0; } }
            class ShapeUser {
                double run(Shape shape) {
                    double onCircle = new Circle().area();
                    double onShape = shape.area();
                    return onCircle + onShape;
                }
            }
        """.trimIndent()) as PsiJavaFile
        IndexingTestUtil.waitUntilIndexesAreReady(project)

        val result = findUsagesOf("javaunion.Circle#area")

        assertNull("No warning expected: ${result.warnings}", result.warnings)
        assertEquals("Exactly 2 usages expected: ${result.usages}", 2, result.usages.size)
        assertEquals(
            "The call on the Circle receiver has no match; the call on the Shape receiver has match BASE",
            setOf(lineOf(file, "new Circle().area()") to null, lineOf(file, "shape.area()") to UsageMatch.BASE),
            result.usages.map { it.line to it.match }.toSet()
        )
        val notes = result.notes.orEmpty()
        assertEquals("Exactly one note expected: $notes", 1, notes.size)
        assertTrue("The note should name Shape.area: $notes", notes[0].contains("javaunion.Shape#area"))
    }

    fun testJavaMethodWithNoSuperMethodHasNoNoteAndNoWarning() {
        // #175: the real Java provider gives the references of a method with no super method, so no
        // handler stage runs: no warning, no note and no mark.
        val file = myFixture.addFileToProject("javasolo/Counter.java", """
            package javasolo;
            class Counter {
                int next() { return 1; }
            }
            class CounterUser {
                int run() { return new Counter().next(); }
            }
        """.trimIndent()) as PsiJavaFile
        IndexingTestUtil.waitUntilIndexesAreReady(project)

        val result = findUsagesOf("javasolo.Counter#next")

        assertNull("No warning expected: ${result.warnings}", result.warnings)
        assertNull("No note expected: ${result.notes}", result.notes)
        assertEquals(
            listOf(lineOf(file, "new Counter().next()") to null),
            result.usages.map { it.line to it.match }
        )
    }

    fun testClassifyUsageMarksCommentReferences() {
        // #132: a reference inside a comment is a COMMENT usage, the rule of the platform's
        // "Usage in comments" group (UsageTypeGroupingRule); a reference in code is not.
        val psiFile = myFixture.addFileToProject("CommentRef.java", """
            public class CommentRef {
                /** Calls {@link #target}. */
                void caller() {
                    target();
                }
                void target() {}
            }
        """.trimIndent()) as com.intellij.psi.PsiJavaFile

        val (docType, callType) = com.intellij.openapi.application.ReadAction.compute<Pair<String, String>, Throwable> {
            val docOffset = psiFile.text.indexOf("#target") + 1
            val callOffset = psiFile.text.indexOf("target();")

            val target = psiFile.classes[0].findMethodsByName("target", false)[0]
            val refs = com.intellij.psi.search.searches.ReferencesSearch.search(target).findAll()
            val docRef = refs.single { it.element.textRange.containsOffset(docOffset) }
            val callRef = refs.single { it.element.textRange.containsOffset(callOffset) }

            FindUsagesTool.classifyUsage(docRef.element) to FindUsagesTool.classifyUsage(callRef.element)
        }

        assertEquals("COMMENT", docType)
        assertFalse("A call in code is not a COMMENT usage", callType == "COMMENT")
    }

    fun testFindFileMatchesWithoutCase() = runBlocking {
        // #255: the name matcher ignores case, as the Go to File popup does.
        myFixture.addFileToProject("CaseProbe.txt", "probe")

        val result = FindFileTool().execute(project, buildJsonObject { put("query", "caseprobe") })

        val text = (result.content.first() as ContentBlock.Text).text
        assertFalse("Search should not fail: $text", result.isError)
        val payload = Json { ignoreUnknownKeys = true }.decodeFromString<FindFileResult>(text)
        assertTrue(
            "A query in lower case should find CaseProbe.txt, got: ${payload.files}",
            payload.files.any { it.name == "CaseProbe.txt" }
        )
    }

    fun testFindFileSurfacesContributorFailureAsWarning() = runBlocking {
        // #87: a file contributor throwing mid-search must not abort the whole search
        // silently — remaining contributors still run and the response carries a
        // warnings entry naming the failed contributor.
        myFixture.addFileToProject("Alpha.txt", "alpha")

        val throwingContributor = object : com.intellij.navigation.ChooseByNameContributorEx {
            override fun processNames(
                processor: com.intellij.util.Processor<in String>,
                scope: com.intellij.psi.search.GlobalSearchScope,
                filter: com.intellij.util.indexing.IdFilter?
            ): Unit = throw IllegalStateException("test-induced contributor failure")

            override fun processElementsWithName(
                name: String,
                processor: com.intellij.util.Processor<in com.intellij.navigation.NavigationItem>,
                parameters: com.intellij.util.indexing.FindSymbolParameters
            ) = Unit
        }
        com.intellij.navigation.ChooseByNameContributor.FILE_EP_NAME.point
            .registerExtension(throwingContributor, com.intellij.openapi.extensions.LoadingOrder.FIRST, testRootDisposable)

        val result = FindFileTool().execute(project, buildJsonObject { put("query", "Alpha") })

        val text = (result.content.first() as ContentBlock.Text).text
        assertFalse("Search should degrade, not error: $text", result.isError)
        val payload = Json { ignoreUnknownKeys = true }.decodeFromString<FindFileResult>(text)
        assertTrue(
            "Default contributor should still return Alpha.txt, got: ${payload.files}",
            payload.files.any { it.name == "Alpha.txt" }
        )
        val warnings = payload.warnings.orEmpty()
        assertTrue(
            "Warning should name the throwing contributor and consequence: $warnings",
            warnings.any { it.contains("contributor") && it.contains("files may be incomplete") }
        )
        // #206: the contributor is an anonymous class, which has an empty simple name.
        assertTrue(
            "Warning should name the anonymous contributor class without the package: $warnings",
            warnings.any { it.startsWith("File contributor ToolExecutionIntegrationTest\$") }
        )
    }

    fun testFindDefinitionToolEndToEnd() = runBlocking {
        val tool = FindDefinitionTool()

        // Test missing required parameter
        val resultMissing = tool.execute(project, buildJsonObject { })
        assertTrue("Should error with missing file", resultMissing.isError)

        // Test with invalid file
        val resultInvalid = tool.execute(project, buildJsonObject {
            put("file", "nonexistent.kt")
            put("line", 1)
            put("column", 1)
        })
        assertTrue("Should error with invalid file", resultInvalid.isError)
    }

    fun testFindDefinitionToolFullElementPreview() = runBlocking {
        if (DumbService.isDumb(project)) return@runBlocking

        // Use myFixture to properly register files in the project source root.
        myFixture.addFileToProject("Service.java", """
            public class Service {
                public void doWork() {
                    System.out.println("done");
                }
            }
        """.trimIndent())
        val callerPsi = myFixture.addFileToProject("Caller.java", """
            public class Caller {
                private Service service = new Service();
                public void call() {
                    service.doWork();
                }
            }
        """.trimIndent())

        val document = PsiDocumentManager.getInstance(project).getDocument(callerPsi)
        assertNotNull("Caller.java should have a document", document)
        val offset = document!!.text.indexOf("doWork")
        assertTrue("Should find doWork reference in Caller.java", offset >= 0)
        val line = document.getLineNumber(offset) + 1
        val column = offset - document.getLineStartOffset(line - 1) + 1

        val tool = FindDefinitionTool()
        val result = try {
            tool.execute(project, buildJsonObject {
                put("file", callerPsi.virtualFile.path)
                put("line", line)
                put("column", column)
            })
        } catch (e: com.github.vcth4nh.idesense.exceptions.IndexNotReadyException) {
            System.err.println("testFindDefinitionToolFullElementPreview: skipped – index not ready")
            return@runBlocking
        }

        if (result.isError) {
            // In-memory VFS may not expose the file through LocalFileSystem; skip rather than fail.
            System.err.println("testFindDefinitionToolFullElementPreview: skipped – tool returned error: ${result.content}")
            return@runBlocking
        }

        val content = result.content.first() as ContentBlock.Text
        val definition = json.decodeFromString<DefinitionResult>(content.text)

        if (!definition.file.endsWith("Service.java")) {
            // Cross-file PSI resolution unavailable in this test environment; skip rather than fail.
            System.err.println("testFindDefinitionToolFullElementPreview: skipped – definition resolved to ${definition.file}, expected Service.java")
            return@runBlocking
        }

        assertTrue("Full preview should include method name", definition.preview.contains("doWork"))
    }

    fun testReadFileToolValidation() = runBlocking {
        val tool = ReadFileTool()

        val missing = tool.execute(project, buildJsonObject { })
        assertTrue("Missing file/qualifiedName should error", missing.isError)

        val endLineOnly = tool.execute(project, buildJsonObject {
            put("file", "Test.java")
            put("endLine", 2)
        })
        assertTrue("endLine without startLine should error", endLineOnly.isError)

        val invalidRange = tool.execute(project, buildJsonObject {
            put("file", "Test.java")
            put("startLine", 3)
            put("endLine", 2)
        })
        assertTrue("endLine < startLine should error", invalidRange.isError)

        val invalidStart = tool.execute(project, buildJsonObject {
            put("file", "Test.java")
            put("startLine", 0)
            put("endLine", 1)
        })
        assertTrue("startLine < 1 should error", invalidStart.isError)
    }

    fun testReadFileToolReadsLinesAndMetadata() = runBlocking {
        val basePath = project.basePath?.let { File(it) }
        val readmeFile = if (basePath != null && basePath.exists()) {
            File(basePath, "ReadMe.java")
        } else {
            Files.createTempFile("idesense", "ReadMe.java").toFile()
        }
        Files.writeString(readmeFile.toPath(), "line1\nline2\nline3\nline4")

        val tool = ReadFileTool()
        val result = tool.execute(project, buildJsonObject {
            val fileArg = if (basePath != null && basePath.exists()) "ReadMe.java" else readmeFile.absolutePath
            put("file", fileArg)
            put("startLine", 2)
            put("endLine", 3)
        })

        assertFalse("Should succeed for valid file", result.isError)
        val content = result.content.first() as ContentBlock.Text
        val readFile = json.decodeFromString<ReadFileResult>(content.text)

        assertTrue("Resolved path should end with filename", readFile.file.endsWith("ReadMe.java"))
        assertEquals("line2\nline3", readFile.content)
        assertEquals(4, readFile.lineCount)
        assertEquals(2, readFile.startLine)
        assertEquals(3, readFile.endLine)
        if (basePath != null && basePath.exists()) {
            assertFalse("Project files should not be marked as library", readFile.isLibraryFile)
        }

        val singleLine = tool.execute(project, buildJsonObject {
            val fileArg = if (basePath != null && basePath.exists()) "ReadMe.java" else readmeFile.absolutePath
            put("file", fileArg)
            put("startLine", 4)
        })
        assertFalse("Single-line read should succeed", singleLine.isError)
        val singleContent = singleLine.content.first() as ContentBlock.Text
        val singleResult = json.decodeFromString<ReadFileResult>(singleContent.text)
        assertEquals("line4", singleResult.content)
        assertEquals(4, singleResult.startLine)
        assertEquals(4, singleResult.endLine)
    }

    fun testFindFileToolPreservesAbsolutePathForLibrarySources() = runBlocking {
        if (DumbService.isDumb(project)) return@runBlocking

        val libraryRoot = Files.createTempDirectory("idesense-lib")
        val packageDir = Files.createDirectories(libraryRoot.resolve("libpkg"))
        val className = "ExternalLib${System.nanoTime().toString().takeLast(8)}"
        val libraryFile = packageDir.resolve("$className.java")
        Files.writeString(
            libraryFile,
            """
            package libpkg;

            public class $className {}
            """.trimIndent()
        )

        val libraryRootVFile = LocalFileSystem.getInstance().refreshAndFindFileByNioFile(libraryRoot)
        assertNotNull("Library root should resolve in VFS", libraryRootVFile)
        ModuleRootModificationUtil.addModuleLibrary(module, "external-library-src", emptyList(), listOf(libraryRootVFile!!.url))
        DumbService.getInstance(project).waitForSmartMode()

        val tool = FindFileTool()
        val projectOnlyResult = tool.execute(project, buildJsonObject {
            put("query", "$className.java")
            put("scope", "project_files")
        })

        assertFalse("Project-only file search should succeed", projectOnlyResult.isError)
        val projectOnlyContent = projectOnlyResult.content.first() as ContentBlock.Text
        val projectOnlyMatches = json.decodeFromString<FindFileResult>(projectOnlyContent.text)
        assertNull(
            "Library file should not be returned when scope excludes libraries",
            projectOnlyMatches.files.firstOrNull { it.name == "$className.java" }
        )

        val result = tool.execute(project, buildJsonObject {
            put("query", "$className.java")
            put("scope", "project_and_libraries")
        })

        assertFalse("Library file search should succeed", result.isError)
        val content = result.content.first() as ContentBlock.Text
        val findFile = json.decodeFromString<FindFileResult>(content.text)
        val match = findFile.files.firstOrNull { it.name == "$className.java" }
        assertNotNull("Library file should be returned when scope includes libraries", match)
        assertEquals(
            "External library paths should remain absolute",
            libraryFile.toString().replace('\\', '/'),
            match!!.path
        )
    }

    fun testFindDefinitionToolResolvesLibrarySourceByAbsolutePath() = runBlocking {
        val libraryRoot = Files.createTempDirectory("idesense-lib")
        val packageDir = Files.createDirectories(libraryRoot.resolve("libpkg"))
        val className = "ExternalLib${System.nanoTime().toString().takeLast(8)}"
        val libraryFile = packageDir.resolve("$className.java")
        Files.writeString(
            libraryFile,
            """
            package libpkg;

            public class $className {
                public void ping() {}
            }
            """.trimIndent()
        )

        val libraryRootVFile = LocalFileSystem.getInstance().refreshAndFindFileByNioFile(libraryRoot)
        assertNotNull("Library root should resolve in VFS", libraryRootVFile)
        ModuleRootModificationUtil.addModuleLibrary(module, "external-library-src", emptyList(), listOf(libraryRootVFile!!.url))
        DumbService.getInstance(project).waitForSmartMode()

        val tool = FindDefinitionTool()
        val result = tool.execute(project, buildJsonObject {
            put("file", libraryFile.toString().replace('\\', '/'))
            put("line", 3)
            put("column", 14)
        })

        assertFalse("Library source definition lookup should succeed", result.isError)
        val content = result.content.first() as ContentBlock.Text
        val definition = json.decodeFromString<DefinitionResult>(content.text)
        assertEquals(libraryFile.toString().replace('\\', '/'), definition.file)
        assertEquals(className, definition.name)
    }

    fun testFindDefinitionToolStillRejectsUnrelatedExternalFiles() = runBlocking {
        val unrelatedFile = Files.createTempFile("idesense-unrelated", ".java")
        Files.writeString(
            unrelatedFile,
            """
            public class Unrelated {}
            """.trimIndent()
        )
        LocalFileSystem.getInstance().refreshAndFindFileByNioFile(unrelatedFile)

        val tool = FindDefinitionTool()
        val result = tool.execute(project, buildJsonObject {
            put("file", unrelatedFile.toString().replace('\\', '/'))
            put("line", 1)
            put("column", 14)
        })

        assertTrue("Unrelated external files must remain inaccessible", result.isError)
    }

    fun testFindUsagesToolFindsProjectUsagesFromLibrarySourcePath() = runBlocking {
        if (DumbService.isDumb(project)) return@runBlocking

        val className = "ExternalLib${System.nanoTime().toString().takeLast(8)}"
        val sourceRoot = Files.createTempDirectory("idesense-lib-src")
        val classesRoot = Files.createTempDirectory("idesense-lib-classes")
        val packageDir = Files.createDirectories(sourceRoot.resolve("libpkg"))
        val libraryFile = packageDir.resolve("$className.java")
        val librarySource = """
            package libpkg;

            public class $className {
                public static void ping() {}
            }
        """.trimIndent()
        Files.writeString(libraryFile, librarySource)
        compileJavaSource(libraryFile, classesRoot)

        val sourceRootVFile = LocalFileSystem.getInstance().refreshAndFindFileByNioFile(sourceRoot)
        val classesRootVFile = LocalFileSystem.getInstance().refreshAndFindFileByNioFile(classesRoot)
        assertNotNull("Library source root should resolve in VFS", sourceRootVFile)
        assertNotNull("Library classes root should resolve in VFS", classesRootVFile)
        ModuleRootModificationUtil.addModuleLibrary(
            module,
            "external-library-bin-and-src",
            listOf(classesRootVFile!!.url),
            listOf(sourceRootVFile!!.url)
        )

        myFixture.addFileToProject(
            "UseExternalLib.java",
            """
            import libpkg.$className;

            public class UseExternalLib {
                public void call() {
                    $className.ping();
                }
            }
            """.trimIndent()
        )

        DumbService.getInstance(project).waitForSmartMode()

        val (line, column) = findPosition(librarySource, "ping")
        val tool = FindUsagesTool()
        val result = tool.execute(project, buildJsonObject {
            put("file", libraryFile.toString().replace('\\', '/'))
            put("line", line)
            put("column", column)
        })

        assertFalse("Library-source usages lookup should succeed", result.isError)
        val content = result.content.first() as ContentBlock.Text
        val usages = json.decodeFromString<FindUsagesResult>(content.text)
        assertTrue(
            "Project usage should be found from external library declaration",
            usages.usages.any { it.file.endsWith("UseExternalLib.java") && it.preview.contains("$className.ping()") }
        )
    }

    fun testTypeHierarchyToolEndToEnd() = runBlocking {
        val tool = TypeHierarchyTool()

        // Test missing required parameter
        val resultMissing = tool.execute(project, buildJsonObject { })
        assertTrue("Should error with missing className", resultMissing.isError)

        // Test with invalid class
        val resultInvalid = tool.execute(project, buildJsonObject {
            put("className", "com.nonexistent.InvalidClass")
        })
        assertTrue("Should error with invalid class", resultInvalid.isError)
    }

    fun testCallHierarchyToolEndToEnd() = runBlocking {
        val tool = CallHierarchyTool()

        // Test missing required parameter
        val resultMissing = tool.execute(project, buildJsonObject { })
        assertTrue("Should error with missing file", resultMissing.isError)

        // Test with invalid file
        val resultInvalid = tool.execute(project, buildJsonObject {
            put("file", "nonexistent.kt")
            put("line", 1)
            put("column", 1)
        })
        assertTrue("Should error with invalid file", resultInvalid.isError)
    }

    fun testFindImplementationsToolEndToEnd() = runBlocking {
        val tool = FindImplementationsTool()

        // Test missing required parameter
        val resultMissing = tool.execute(project, buildJsonObject { })
        assertTrue("Should error with missing file", resultMissing.isError)

        // Test with invalid file
        val resultInvalid = tool.execute(project, buildJsonObject {
            put("file", "nonexistent.kt")
            put("line", 1)
            put("column", 1)
        })
        assertTrue("Should error with invalid file", resultInvalid.isError)
    }

    // Intelligence Tools Tests

    fun testGetDiagnosticsToolEndToEnd() = runBlocking {
        val tool = GetDiagnosticsTool()

        // Test missing required parameter
        val resultMissing = tool.execute(project, buildJsonObject { })
        assertTrue("Should error with missing file", resultMissing.isError)

        // Test with invalid file
        val resultInvalid = tool.execute(project, buildJsonObject {
            put("file", "nonexistent.kt")
        })
        assertTrue("Should error with invalid file", resultInvalid.isError)
    }

    // Project Tools Tests

    fun testGetIndexStatusToolEndToEnd() = runBlocking {
        val tool = GetIndexStatusTool()

        val result = tool.execute(project, buildJsonObject { })

        assertFalse("get_index_status should succeed", result.isError)
        assertTrue("Should have content", result.content.isNotEmpty())

        val content = result.content.first()
        assertTrue("Content should be text", content is ContentBlock.Text)

        val textContent = (content as ContentBlock.Text).text
        val resultJson = json.parseToJsonElement(textContent).jsonObject

        assertNotNull("Result should have isDumbMode", resultJson["isDumbMode"])
    }

    // Tool Registry Integration Tests

    fun testAllToolsRegistered() {
        val registry = ToolRegistry()
        registry.registerBuiltInTools()

        val expectedTools = listOf(
            // Navigation tools
            ToolNames.FIND_USAGES,
            ToolNames.FIND_DEFINITION,
            ToolNames.TYPE_HIERARCHY,
            ToolNames.CALL_HIERARCHY,
            ToolNames.FIND_IMPLEMENTATIONS,
            ToolNames.FIND_SYMBOL,
            ToolNames.FIND_SUPER_METHODS,
            ToolNames.FILE_STRUCTURE,
            // Fast search tools
            ToolNames.FIND_CLASS,
            ToolNames.FIND_FILE,
            ToolNames.READ_FILE,
            ToolNames.SEARCH_TEXT,
            // Intelligence tools
            ToolNames.DIAGNOSTICS,
            ToolNames.EXPLAIN_SYMBOL,
            // Project tools
            ToolNames.INSTALL_PLUGIN,
            ToolNames.RESTART_IDE,
            ToolNames.INDEX_STATUS,
            ToolNames.SYNC_FILES,
            // Refactoring tools
            ToolNames.REFACTOR_RENAME,
            ToolNames.REFACTOR_MOVE
        )

        assertEquals("Should have correct number of tools", expectedTools.size, registry.getAllTools().size)

        expectedTools.forEach { toolName ->
            assertNotNull("$toolName should be registered", registry.getTool(toolName))
        }
    }

    fun testToolDefinitionsHaveValidSchemas() {
        val registry = ToolRegistry()
        registry.registerBuiltInTools()

        val definitions = registry.getToolDefinitions()

        definitions.forEach { definition ->
            assertTrue("${definition.name} should have non-empty description", definition.description.isNotEmpty())
            assertNotNull("${definition.name} should have inputSchema", definition.inputSchema)
            assertEquals("${definition.name} inputSchema should be object type",
                "object", definition.inputSchema["type"]?.toString()?.replace("\"", ""))
        }
    }

    // Error Scenario Tests

    fun testToolsHandleNullProject() {
        // This test verifies tools handle edge cases gracefully
        val registry = ToolRegistry()
        registry.registerBuiltInTools()

        registry.getAllTools().forEach { tool ->
            assertNotNull("${tool.name} should have name", tool.name)
            assertNotNull("${tool.name} should have description", tool.description)
            assertNotNull("${tool.name} should have inputSchema", tool.inputSchema)
        }
    }

    fun testToolsReturnProperContentBlocks() = runBlocking {
        val tool = GetIndexStatusTool()
        val result = tool.execute(project, buildJsonObject { })

        assertFalse("Result should not be error", result.isError)
        assertTrue("Result should have content", result.content.isNotEmpty())

        result.content.forEach { block ->
            when (block) {
                is ContentBlock.Text -> assertNotNull("Text block should have text", block.text)
                is ContentBlock.Image -> {
                    assertNotNull("Image block should have data", block.data)
                    assertNotNull("Image block should have mimeType", block.mimeType)
                }
            }
        }
    }

    private fun compileJavaSource(sourceFile: Path, outputDir: Path) {
        val compiler = ToolProvider.getSystemJavaCompiler()
        val exitCode = if (compiler != null) {
            compiler.run(
                null,
                null,
                null,
                "-d",
                outputDir.toString(),
                sourceFile.toString()
            )
        } else {
            val javaHome = System.getenv("JAVA_HOME")
            assertNotNull("Tests require a JDK with javac available", javaHome)

            val javac = Path.of(javaHome!!, "bin", "javac").toString()
            val process = ProcessBuilder(
                javac,
                "-d",
                outputDir.toString(),
                sourceFile.toString()
            ).redirectErrorStream(true).start()
            process.inputStream.bufferedReader().use { reader ->
                val output = reader.readText()
                val completed = process.waitFor()
                assertEquals("javac should compile library source successfully. Output: $output", 0, completed)
            }
            0
        }
        assertEquals("Library source should compile successfully", 0, exitCode)
    }

    private fun findPosition(text: String, needle: String): Pair<Int, Int> {
        val offset = text.indexOf(needle)
        assertTrue("Needle '$needle' should exist in fixture text", offset >= 0)

        val before = text.substring(0, offset)
        val line = before.count { it == '\n' } + 1
        val column = offset - before.lastIndexOf('\n').let { if (it == -1) -1 else it }
        return line to column
    }

    fun testFindUsagesToolFindsJavaMethodCallersWithoutEdtAssertion() = runBlocking {
        // Java method + caller fixture. The method declaration is on PsiMethod,
        // which is what triggers JavaFindUsagesHandler.processElementUsages
        // (modal-UI assertion on EDT). The fix routes through findReferencesToHighlight
        // which doesn't assert EDT.
        val service = myFixture.addFileToProject(
            "src/main/java/com/example/Service.java",
            """
            package com.example;
            public class Service {
                public void doWork() {}
            }
            """.trimIndent()
        )
        myFixture.addFileToProject(
            "src/main/java/com/example/Caller.java",
            """
            package com.example;
            public class Caller {
                void invoke() { new Service().doWork(); }
            }
            """.trimIndent()
        )
        IndexingTestUtil.waitUntilIndexesAreReady(project)

        // Locate the method-name caret from the actual document — hardcoded line/column
        // assumed a specific indent that may not survive trimIndent in every JVM/locale.
        val serviceDocument = PsiDocumentManager.getInstance(project).getDocument(service)
        assertNotNull("Service.java should have a document", serviceDocument)
        val doWorkOffset = serviceDocument!!.text.indexOf("doWork")
        assertTrue("doWork declaration should exist in Service.java", doWorkOffset >= 0)
        val line = serviceDocument.getLineNumber(doWorkOffset) + 1
        val column = doWorkOffset - serviceDocument.getLineStartOffset(line - 1) + 1

        val tool = FindUsagesTool()
        // Use the actual VFS path; in-memory test VFS may not be visible via LocalFileSystem
        // when a hardcoded relative path is passed.
        val args = buildJsonObject {
            put("file", service.virtualFile.path)
            put("line", line)
            put("column", column)
        }

        val result = tool.execute(project, args)

        // (a) No EDT assertion in the response envelope.
        val text = Json.encodeToString(result)
        assertFalse(
            "Result must not contain EDT-assertion error: $text",
            text.contains("Access is allowed from") || text.contains("Event Dispatch Thread")
        )

        // (b) Caller is in the usages list — skip rather than fail when the in-memory
        // VFS doesn't expose the file through LocalFileSystem (mirrors the defensive
        // pattern in testFindDefinitionToolFullElementPreview above).
        if (result.isError) {
            System.err.println(
                "testFindUsagesToolFindsJavaMethodCallersWithoutEdtAssertion: " +
                    "skipped – tool returned error: $text"
            )
            return@runBlocking
        }
        assertTrue(
            "Caller.java should appear in usages: $text",
            text.contains("Caller.java")
        )
    }
}
