package com.github.vcth4nh.idesense.models

import com.github.vcth4nh.idesense.tools.models.*
import junit.framework.TestCase
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.encodeToJsonElement
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

class ToolModelsUnitTest : TestCase() {

    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    // PositionInput tests

    fun testPositionInputSerialization() {
        val input = PositionInput(
            file = "src/main/kotlin/Main.kt",
            line = 10,
            column = 5
        )

        val serialized = json.encodeToString(input)
        val deserialized = json.decodeFromString<PositionInput>(serialized)

        assertEquals("src/main/kotlin/Main.kt", deserialized.file)
        assertEquals(10, deserialized.line)
        assertEquals(5, deserialized.column)
    }

    // UsageLocation tests

    fun testUsageLocationSerialization() {
        val location = UsageLocation(
            file = "src/Service.kt",
            line = 25,
            column = 12,
            preview = "val service = UserService()",
            usageType = "METHOD_CALL",
            enclosingScope = listOf("MyClass", "myMethod")
        )

        val serialized = json.encodeToString(location)
        val deserialized = json.decodeFromString<UsageLocation>(serialized)

        assertEquals("src/Service.kt", deserialized.file)
        assertEquals(25, deserialized.line)
        assertEquals(12, deserialized.column)
        assertEquals("val service = UserService()", deserialized.preview)
        assertEquals("METHOD_CALL", deserialized.usageType)
        assertEquals(listOf("MyClass", "myMethod"), deserialized.enclosingScope)
    }

    // FindUsagesResult tests

    fun testFindUsagesResultSerialization() {
        val result = FindUsagesResult(
            usages = listOf(
                UsageLocation("file1.kt", 10, 5, "context1", "REFERENCE", listOf("ClassA", "methodX")),
                UsageLocation("file2.kt", 20, 8, "context2", "METHOD_CALL", listOf("ClassB", "methodY"))
            ),
            totalCollected = 2
        )

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<FindUsagesResult>(serialized)

        assertEquals(2, deserialized.usages.size)
        assertEquals(2, deserialized.totalCollected)
    }

    fun testFindUsagesResultEmpty() {
        val result = FindUsagesResult(usages = emptyList(), totalCollected = 0)

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<FindUsagesResult>(serialized)

        assertTrue(deserialized.usages.isEmpty())
        assertEquals(0, deserialized.totalCollected)
    }

    // DefinitionResult tests

    fun testDefinitionResultSerialization() {
        val result = DefinitionResult(
            file = "src/model/User.kt",
            line = 5,
            column = 1,
            name = "User",
            kind = "DATA_CLASS",
            preview = "data class User(val name: String)",
            qualifiedName = "com.example.User",
            enclosingScope = null
        )

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<DefinitionResult>(serialized)

        assertEquals("src/model/User.kt", deserialized.file)
        assertEquals(5, deserialized.line)
        assertEquals(1, deserialized.column)
        assertEquals("data class User(val name: String)", deserialized.preview)
        assertEquals("User", deserialized.name)
        assertEquals("DATA_CLASS", deserialized.kind)
        assertEquals("com.example.User", deserialized.qualifiedName)
        assertNull(deserialized.enclosingScope)
    }

    // TypeHierarchyResult tests

    fun testTypeHierarchyResultSerialization() {
        val result = TypeHierarchyResult(
            element = TypeElement(name = "MyService", kind = "CLASS", file = "src/MyService.kt", line = 4, column = 7),
            supertypes = listOf(
                TypeElement(name = "BaseService", kind = "CLASS", file = "src/BaseService.kt", line = 4, column = 7),
                TypeElement(name = "Service", kind = "INTERFACE", file = null, line = null, column = null)
            ),
            subtypes = listOf(
                TypeElement(name = "SpecialService", kind = "CLASS", file = "src/SpecialService.kt", line = 4, column = 7)
            )
        )

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<TypeHierarchyResult>(serialized)

        assertEquals("MyService", deserialized.element.name)
        assertEquals(2, deserialized.supertypes.size)
        assertEquals(1, deserialized.subtypes.size)
    }

    // TypeElement tests

    fun testTypeElementWithNestedSupertypes() {
        val element = TypeElement(
            name = "Child",
            qualifiedName = "demo.Child",
            kind = "CLASS",
            file = "Child.kt",
            line = 4,
            column = 7,
            supertypes = listOf(
                TypeElement(
                    name = "Parent",
                    qualifiedName = "demo.Parent",
                    kind = "CLASS",
                    file = "Parent.kt",
                    line = 4,
                    column = 7,
                    supertypes = listOf(
                        TypeElement(
                            name = "GrandParent",
                            qualifiedName = "demo.GrandParent",
                            kind = "CLASS",
                            file = "GrandParent.kt",
                            line = 4,
                            column = 7
                        )
                    )
                )
            )
        )

        val serialized = json.encodeToString(element)
        val deserialized = json.decodeFromString<TypeElement>(serialized)

        assertEquals("Child", deserialized.name)
        assertEquals("demo.Child", deserialized.qualifiedName)
        assertNotNull(deserialized.supertypes)
        assertEquals(1, deserialized.supertypes!!.size)
        assertEquals("Parent", deserialized.supertypes!![0].name)
        assertEquals(1, deserialized.supertypes!![0].supertypes!!.size)
    }

    fun testTypeElementWithNullFile() {
        val element = TypeElement(
            name = "Serializable",
            kind = "INTERFACE",
            file = null,
            line = null,
            column = null
        )

        val serialized = json.encodeToString(element)
        val deserialized = json.decodeFromString<TypeElement>(serialized)

        assertEquals("Serializable", deserialized.name)
        assertNull(deserialized.file)
        assertNull(deserialized.line)
        assertNull(deserialized.column)
        assertEquals("INTERFACE", deserialized.kind)
    }

    // CallHierarchyResult tests

    fun testCallHierarchyResultSerialization() {
        val result = CallHierarchyResult(
            element = CallElement(name = "processData", kind = "METHOD", file = "src/Processor.kt", line = 50, column = 1),
            calls = listOf(
                CallElement(name = "validateInput", kind = "METHOD", file = "src/Validator.kt", line = 30, column = 1),
                CallElement(name = "saveResult", kind = "METHOD", file = "src/Repository.kt", line = 100, column = 1)
            )
        )

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<CallHierarchyResult>(serialized)

        assertEquals("processData", deserialized.element.name)
        assertEquals(2, deserialized.calls.size)
    }

    // CallElement tests

    fun testCallElementWithChildren() {
        val element = CallElement(
            name = "main",
            kind = "FUNCTION",
            file = "Main.kt",
            line = 5,
            column = 1,
            children = listOf(
                CallElement(name = "init", kind = "FUNCTION", file = "Init.kt", line = 10, column = 1, children = listOf(
                    CallElement(name = "loadConfig", kind = "FUNCTION", file = "Config.kt", line = 15, column = 1)
                )),
                CallElement(name = "run", kind = "FUNCTION", file = "Runner.kt", line = 20, column = 1)
            )
        )

        val serialized = json.encodeToString(element)
        val deserialized = json.decodeFromString<CallElement>(serialized)

        assertEquals("main", deserialized.name)
        assertNotNull(deserialized.children)
        assertEquals(2, deserialized.children!!.size)
        assertEquals(1, deserialized.children!![0].children!!.size)
    }

    // ImplementationResult tests

    fun testImplementationResultSerialization() {
        val result = ImplementationResult(
            implementations = listOf(
                ImplementationLocation("UserRepositoryImpl", "src/impl/UserRepositoryImpl.kt", 15, 1, "CLASS"),
                ImplementationLocation("MockUserRepository", "src/test/MockUserRepository.kt", 8, 1, "CLASS")
            ),
            totalCollected = 2
        )

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<ImplementationResult>(serialized)

        assertEquals(2, deserialized.implementations.size)
        assertEquals(2, deserialized.totalCollected)
        assertEquals("UserRepositoryImpl", deserialized.implementations[0].name)
    }

    // ImplementationLocation tests

    fun testImplementationLocationSerialization() {
        val location = ImplementationLocation(
            name = "ServiceImpl",
            file = "src/ServiceImpl.java",
            line = 10,
            column = 5,
            kind = "CLASS"
        )

        val serialized = json.encodeToString(location)
        val deserialized = json.decodeFromString<ImplementationLocation>(serialized)

        assertEquals("ServiceImpl", deserialized.name)
        assertEquals("src/ServiceImpl.java", deserialized.file)
        assertEquals(10, deserialized.line)
        assertEquals(5, deserialized.column)
        assertEquals("CLASS", deserialized.kind)
    }

    // DiagnosticsResult tests

    fun testDiagnosticsResultSerialization() {
        val result = DiagnosticsResult(
            problems = listOf(
                ProblemInfo("Unused variable", "WARNING", "Main.kt", 10, 5, 10, 15)
            ),
            intentions = listOf(
                IntentionInfo("Add import", "Import the required class")
            ),
            problemCount = 1,
            intentionCount = 1
        )

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<DiagnosticsResult>(serialized)

        assertEquals(1, deserialized.problemCount)
        assertEquals(1, deserialized.intentionCount)
        assertEquals("Unused variable", deserialized.problems!![0].message)
        assertEquals("Add import", deserialized.intentions!![0].name)
    }

    // TestResultInfo tests

    fun testTestResultInfoSerialization() {
        val info = TestResultInfo(
            name = "testLogin",
            suite = "UserServiceTest",
            status = "FAILED",
            durationMs = 142,
            errorMessage = "Expected true but was false",
            stacktrace = "at UserServiceTest.testLogin(UserServiceTest.java:42)",
            file = "src/test/UserServiceTest.java",
            line = 42
        )

        val serialized = json.encodeToString(info)
        val deserialized = json.decodeFromString<TestResultInfo>(serialized)

        assertEquals("testLogin", deserialized.name)
        assertEquals("UserServiceTest", deserialized.suite)
        assertEquals("FAILED", deserialized.status)
        assertEquals(142L, deserialized.durationMs)
        assertEquals("Expected true but was false", deserialized.errorMessage)
        assertNotNull(deserialized.stacktrace)
        assertEquals("src/test/UserServiceTest.java", deserialized.file)
        assertEquals(42, deserialized.line)
    }

    fun testTestResultInfoPassed() {
        val info = TestResultInfo(
            name = "testBasic",
            suite = "BasicTest",
            status = "PASSED",
            durationMs = 5,
            errorMessage = null,
            stacktrace = null,
            file = "src/test/BasicTest.java",
            line = 10
        )

        val serialized = json.encodeToString(info)
        val deserialized = json.decodeFromString<TestResultInfo>(serialized)

        assertEquals("PASSED", deserialized.status)
        assertNull(deserialized.errorMessage)
        assertNull(deserialized.stacktrace)
    }

    fun testTestResultInfoNullLocation() {
        val info = TestResultInfo(
            name = "testSomething",
            suite = null,
            status = "IGNORED",
            durationMs = null,
            errorMessage = null,
            stacktrace = null,
            file = null,
            line = null
        )

        val serialized = json.encodeToString(info)
        val deserialized = json.decodeFromString<TestResultInfo>(serialized)

        assertNull(deserialized.suite)
        assertNull(deserialized.file)
        assertNull(deserialized.line)
        assertNull(deserialized.durationMs)
    }

    fun testTestResultInfoAllStatuses() {
        val statuses = listOf("PASSED", "FAILED", "IGNORED", "ERROR")

        statuses.forEach { status ->
            val info = TestResultInfo("test", "Suite", status, 1, null, null, null, null)
            val serialized = json.encodeToString(info)
            val deserialized = json.decodeFromString<TestResultInfo>(serialized)
            assertEquals(status, deserialized.status)
        }
    }

    // TestSummary tests

    fun testTestSummarySerialization() {
        val summary = TestSummary(
            total = 46,
            passed = 42,
            failed = 3,
            ignored = 1,
            runConfigName = "All Tests"
        )

        val serialized = json.encodeToString(summary)
        val deserialized = json.decodeFromString<TestSummary>(serialized)

        assertEquals(46, deserialized.total)
        assertEquals(42, deserialized.passed)
        assertEquals(3, deserialized.failed)
        assertEquals(1, deserialized.ignored)
        assertEquals("All Tests", deserialized.runConfigName)
    }

    fun testTestSummaryNullRunConfig() {
        val summary = TestSummary(total = 10, passed = 10, failed = 0, ignored = 0, runConfigName = null)

        val serialized = json.encodeToString(summary)
        val deserialized = json.decodeFromString<TestSummary>(serialized)

        assertNull(deserialized.runConfigName)
    }

    // Enhanced DiagnosticsResult tests

    fun testDiagnosticsResultWithBuildErrors() {
        val result = DiagnosticsResult(
            buildErrors = listOf(
                BuildMessage("ERROR", "Unresolved reference: foo", "src/Main.kt", 25, 12)
            ),
            buildErrorCount = 1,
            buildWarningCount = 0,
            buildErrorsTruncated = false,
            buildTimestamp = 1711800000000L
        )

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<DiagnosticsResult>(serialized)

        assertNull(deserialized.problems)
        assertNull(deserialized.intentions)
        assertNotNull(deserialized.buildErrors)
        assertEquals(1, deserialized.buildErrors!!.size)
        assertEquals(1711800000000L, deserialized.buildTimestamp)
        assertFalse(deserialized.buildErrorsTruncated!!)
    }

    // BuildMessage tests

    fun testBuildMessageSerializationNullFields() {
        val msg = BuildMessage(
            category = "ERROR",
            message = "Something failed"
        )

        val jsonString = json.encodeToString(msg)
        val decoded = json.decodeFromString<BuildMessage>(jsonString)
        assertEquals("ERROR", decoded.category)
        assertEquals("Something failed", decoded.message)
        assertNull(decoded.file)
        assertNull(decoded.line)
        assertNull(decoded.column)
    }

    fun testBuildMessageSerializationAllFields() {
        val msg = BuildMessage(
            category = "WARNING",
            message = "Unused import",
            file = "src/main/Foo.kt",
            line = 3,
            column = 1
        )

        val jsonString = json.encodeToString(msg)
        val decoded = json.decodeFromString<BuildMessage>(jsonString)
        assertEquals(msg, decoded)
    }

    fun testDiagnosticsResultWithTestResults() {
        val result = DiagnosticsResult(
            testResults = listOf(
                TestResultInfo("testLogin", "AuthTest", "FAILED", 100, "assertion failed", null, "AuthTest.kt", 10)
            ),
            testSummary = TestSummary(total = 5, passed = 4, failed = 1, ignored = 0, runConfigName = "Tests"),
            testResultsTruncated = false
        )

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<DiagnosticsResult>(serialized)

        assertNull(deserialized.problems)
        assertNull(deserialized.buildErrors)
        assertNotNull(deserialized.testResults)
        assertEquals(1, deserialized.testResults!!.size)
        assertEquals(5, deserialized.testSummary!!.total)
    }

    fun testDiagnosticsResultAllSourcesCombined() {
        val result = DiagnosticsResult(
            problems = listOf(ProblemInfo("Unused variable", "WARNING", "Main.kt", 10, 5, 10, 15)),
            intentions = listOf(IntentionInfo("Remove variable", null)),
            problemCount = 1,
            intentionCount = 1,
            buildErrors = listOf(BuildMessage("ERROR", "Build failed", "Main.kt", 10, 5)),
            buildErrorCount = 1,
            buildWarningCount = 0,
            buildErrorsTruncated = false,
            buildTimestamp = 1711800000000L,
            testResults = listOf(TestResultInfo("test1", "Suite1", "PASSED", 5, null, null, null, null)),
            testSummary = TestSummary(1, 1, 0, 0, "Test"),
            testResultsTruncated = false
        )

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<DiagnosticsResult>(serialized)

        assertNotNull(deserialized.problems)
        assertNotNull(deserialized.buildErrors)
        assertNotNull(deserialized.testResults)
    }

    fun testDiagnosticsResultAllNulls() {
        val result = DiagnosticsResult()

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<DiagnosticsResult>(serialized)

        assertNull(deserialized.problems)
        assertNull(deserialized.intentions)
        assertNull(deserialized.buildErrors)
        assertNull(deserialized.testResults)
        assertNull(deserialized.buildTimestamp)
    }

    // ProblemInfo tests

    fun testProblemInfoWithNullEndPositions() {
        val problem = ProblemInfo(
            message = "Syntax error",
            severity = "ERROR",
            file = "Broken.kt",
            line = 5,
            column = 10,
            endLine = null,
            endColumn = null
        )

        val serialized = json.encodeToString(problem)
        val deserialized = json.decodeFromString<ProblemInfo>(serialized)

        assertEquals("Syntax error", deserialized.message)
        assertEquals("ERROR", deserialized.severity)
        assertNull(deserialized.endLine)
        assertNull(deserialized.endColumn)
    }

    fun testProblemInfoAllSeverities() {
        val severities = listOf("ERROR", "WARNING", "WEAK_WARNING", "INFO")

        severities.forEach { severity ->
            val problem = ProblemInfo("Test", severity, "file.kt", 1, 1, 1, 10)
            val serialized = json.encodeToString(problem)
            val deserialized = json.decodeFromString<ProblemInfo>(serialized)
            assertEquals(severity, deserialized.severity)
        }
    }

    // IntentionInfo tests

    fun testIntentionInfoWithDescription() {
        val intention = IntentionInfo(
            name = "Convert to expression body",
            description = "Simplify function by converting to expression body"
        )

        val serialized = json.encodeToString(intention)
        val deserialized = json.decodeFromString<IntentionInfo>(serialized)

        assertEquals("Convert to expression body", deserialized.name)
        assertEquals("Simplify function by converting to expression body", deserialized.description)
    }

    fun testIntentionInfoWithoutDescription() {
        val intention = IntentionInfo(
            name = "Quick fix",
            description = null
        )

        val serialized = json.encodeToString(intention)
        val deserialized = json.decodeFromString<IntentionInfo>(serialized)

        assertEquals("Quick fix", deserialized.name)
        assertNull(deserialized.description)
    }

    // RefactoringResult tests

    fun testRefactoringResultSuccess() {
        val result = RefactoringResult(
            success = true,
            affectedFiles = listOf("src/Main.kt", "src/Service.kt", "test/MainTest.kt"),
            changesCount = 5,
            message = "Renamed 'foo' to 'bar' in 3 files"
        )

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<RefactoringResult>(serialized)

        assertTrue(deserialized.success)
        assertEquals(3, deserialized.affectedFiles.size)
        assertEquals(5, deserialized.changesCount)
        assertTrue(deserialized.message.contains("Renamed"))
    }

    fun testRefactoringResultFailure() {
        val result = RefactoringResult(
            success = false,
            affectedFiles = emptyList(),
            changesCount = 0,
            message = "Cannot rename: symbol has usages in read-only files"
        )

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<RefactoringResult>(serialized)

        assertFalse(deserialized.success)
        assertTrue(deserialized.affectedFiles.isEmpty())
        assertEquals(0, deserialized.changesCount)
    }

    // IndexStatusResult tests

    fun testIndexStatusResultSmartMode() {
        val result = IndexStatusResult(isDumbMode = false)

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<IndexStatusResult>(serialized)

        assertFalse(deserialized.isDumbMode)
    }

    fun testIndexStatusResultDumbMode() {
        val result = IndexStatusResult(isDumbMode = true)

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<IndexStatusResult>(serialized)

        assertTrue(deserialized.isDumbMode)
    }

    // #31 — ide_index_status must expose only isDumbMode; the derived isIndexing (which mirrored
    // isDumbMode) and the always-null indexingProgress are removed.
    fun testIndexStatusResultOmitsDerivedFields() {
        val obj = json.encodeToJsonElement(
            IndexStatusResult(isDumbMode = true)
        ).jsonObject
        assertTrue("isDumbMode must remain", obj.containsKey("isDumbMode"))
        assertFalse("isIndexing must be removed", obj.containsKey("isIndexing"))
        assertFalse("indexingProgress must be removed", obj.containsKey("indexingProgress"))
    }

    // FindSymbolResult tests

    fun testFindSymbolResultSerialization() {
        val result = FindSymbolResult(
            symbols = listOf(
                SymbolMatch("UserService", "com.example.UserService", "CLASS", "src/UserService.kt", 10, 1),
                SymbolMatch("findById", "com.example.UserRepository#findById(java.lang.Long)", "METHOD", "src/UserRepository.kt", 25, 1)
            ),
            totalCollected = 2,
            query = "User"
        )

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<FindSymbolResult>(serialized)

        assertEquals(2, deserialized.symbols.size)
        assertEquals(2, deserialized.totalCollected)
        assertEquals("User", deserialized.query)
    }

    fun testFindSymbolResultEmpty() {
        val result = FindSymbolResult(symbols = emptyList(), totalCollected = 0, query = "NonExistent")

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<FindSymbolResult>(serialized)

        assertTrue(deserialized.symbols.isEmpty())
        assertEquals(0, deserialized.totalCollected)
        assertEquals("NonExistent", deserialized.query)
    }

    // SymbolMatch tests

    fun testSymbolMatchSerialization() {
        val match = SymbolMatch(
            name = "UserService",
            qualifiedName = "com.example.service.UserService",
            kind = "INTERFACE",
            file = "src/main/java/com/example/service/UserService.java",
            line = 12,
            column = 8
        )

        val serialized = json.encodeToString(match)
        val deserialized = json.decodeFromString<SymbolMatch>(serialized)

        assertEquals("UserService", deserialized.name)
        assertEquals("com.example.service.UserService", deserialized.qualifiedName)
        assertEquals("INTERFACE", deserialized.kind)
        assertEquals("src/main/java/com/example/service/UserService.java", deserialized.file)
        assertEquals(12, deserialized.line)
        assertEquals(8, deserialized.column)
    }

    fun testSymbolMatchAllKinds() {
        val kinds = listOf("CLASS", "INTERFACE", "ENUM", "ANNOTATION", "RECORD", "ABSTRACT_CLASS", "METHOD", "FIELD")

        kinds.forEach { kind ->
            val match = SymbolMatch("Test", "com.Test", kind, "file.kt", 1, 1)
            val serialized = json.encodeToString(match)
            val deserialized = json.decodeFromString<SymbolMatch>(serialized)
            assertEquals(kind, deserialized.kind)
        }
    }

    // SuperMethodsResult tests

    fun testSuperMethodsResultSerialization() {
        val result = SuperMethodsResult(
            method = MethodInfo(
                name = "findUser",
                qualifiedName = "com.example.UserServiceImpl#findUser",
                kind = "METHOD",
                file = "src/UserServiceImpl.kt",
                line = 25,
                column = 5
            ),
            hierarchy = listOf(
                SuperMethodInfo(
                    name = "findUser",
                    qualifiedName = "com.example.UserService#findUser",
                    kind = "METHOD",
                    file = "src/UserService.kt",
                    line = 15,
                    column = 5,
                )
            ),
        )

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<SuperMethodsResult>(serialized)

        assertEquals("findUser", deserialized.method.name)
        assertEquals(1, deserialized.hierarchy.size)
    }

    fun testSuperMethodsResultEmpty() {
        val result = SuperMethodsResult(
            method = MethodInfo(
                name = "helperMethod",
                qualifiedName = "com.example.Service#helperMethod",
                kind = "METHOD",
                file = "file.kt",
                line = 50,
                column = 1
            ),
            hierarchy = emptyList(),
        )

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<SuperMethodsResult>(serialized)

        assertTrue(deserialized.hierarchy.isEmpty())
    }

    // MethodInfo tests

    fun testMethodInfoSerialization() {
        val info = MethodInfo(
            name = "processData",
            qualifiedName = "com.example.DataProcessor#processData",
            kind = "METHOD",
            file = "src/DataProcessor.kt",
            line = 100,
            column = 12
        )

        val serialized = json.encodeToString(info)
        val deserialized = json.decodeFromString<MethodInfo>(serialized)

        assertEquals("processData", deserialized.name)
        assertEquals("com.example.DataProcessor#processData", deserialized.qualifiedName)
        assertEquals("METHOD", deserialized.kind)
        assertEquals("src/DataProcessor.kt", deserialized.file)
        assertEquals(100, deserialized.line)
        assertEquals(12, deserialized.column)
    }

    // SuperMethodInfo tests

    fun testSuperMethodInfoSerialization() {
        val info = SuperMethodInfo(
            name = "save",
            qualifiedName = "com.example.Repository#save",
            kind = "METHOD",
            file = "src/Repository.kt",
            line = 8,
            column = 5,
        )

        val serialized = json.encodeToString(info)
        val deserialized = json.decodeFromString<SuperMethodInfo>(serialized)

        assertEquals("save", deserialized.name)
        assertEquals("com.example.Repository#save", deserialized.qualifiedName)
        assertEquals("METHOD", deserialized.kind)
        assertEquals(5, deserialized.column)
    }

    fun testSuperMethodInfoWithNullFile() {
        val info = SuperMethodInfo(
            name = "toString",
            qualifiedName = "java.lang.Object#toString",
            kind = "METHOD",
            file = null,
            line = null,
            column = null,
        )

        val serialized = json.encodeToString(info)
        val deserialized = json.decodeFromString<SuperMethodInfo>(serialized)

        assertEquals("toString", deserialized.name)
        assertEquals("java.lang.Object#toString", deserialized.qualifiedName)
        assertEquals("METHOD", deserialized.kind)
        assertNull(deserialized.file)
        assertNull(deserialized.line)
        assertNull(deserialized.column)
    }

    fun testSuperMethodInfoMultiLevelHierarchy() {
        val hierarchy = listOf(
            SuperMethodInfo("save", "AbstractRepo#save", "METHOD", "file1.kt", 20, 1),
            SuperMethodInfo("save", "BaseRepo#save", "METHOD", "file2.kt", 15, 1),
            SuperMethodInfo("save", "Repository#save", "METHOD", "file3.kt", 8, 1)
        )

        val result = SuperMethodsResult(
            method = MethodInfo("save", "UserRepo#save", "METHOD", "file0.kt", 30, 1),
            hierarchy = hierarchy,
        )

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<SuperMethodsResult>(serialized)

        assertEquals(3, deserialized.hierarchy.size)
        assertEquals("AbstractRepo#save", deserialized.hierarchy[0].qualifiedName)
        assertEquals("BaseRepo#save", deserialized.hierarchy[1].qualifiedName)
        assertEquals("Repository#save", deserialized.hierarchy[2].qualifiedName)
    }

    // FindClassResult tests

    fun testFindClassResultSerialization() {
        val result = FindClassResult(
            classes = listOf(
                SymbolMatch("UserService", "com.example.UserService", "CLASS", "src/UserService.kt", 10, 1),
                SymbolMatch("UserRepository", "com.example.UserRepository", "INTERFACE", "src/UserRepository.kt", 15, 1)
            ),
            totalCollected = 2,
            query = "User"
        )

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<FindClassResult>(serialized)

        assertEquals(2, deserialized.classes.size)
        assertEquals(2, deserialized.totalCollected)
        assertEquals("User", deserialized.query)
        assertEquals("UserService", deserialized.classes[0].name)
    }

    fun testFindClassResultEmpty() {
        val result = FindClassResult(classes = emptyList(), totalCollected = 0, query = "NonExistent")

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<FindClassResult>(serialized)

        assertTrue(deserialized.classes.isEmpty())
        assertEquals(0, deserialized.totalCollected)
        assertEquals("NonExistent", deserialized.query)
    }

    // FindFileResult tests

    fun testFindFileResultSerialization() {
        val result = FindFileResult(
            files = listOf(
                FileMatch("UserService.kt", "src/main/kotlin/UserService.kt", "src/main/kotlin"),
                FileMatch("build.gradle", "build.gradle", "")
            ),
            totalCollected = 2,
            query = "User"
        )

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<FindFileResult>(serialized)

        assertEquals(2, deserialized.files.size)
        assertEquals(2, deserialized.totalCollected)
        assertEquals("User", deserialized.query)
        assertEquals("UserService.kt", deserialized.files[0].name)
    }

    fun testFindFileResultEmpty() {
        val result = FindFileResult(files = emptyList(), totalCollected = 0, query = "NonExistent.txt")

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<FindFileResult>(serialized)

        assertTrue(deserialized.files.isEmpty())
        assertEquals(0, deserialized.totalCollected)
    }

    // FileMatch tests

    fun testFileMatchSerialization() {
        val match = FileMatch(
            name = "Main.kt",
            path = "src/main/kotlin/Main.kt",
            directory = "src/main/kotlin"
        )

        val serialized = json.encodeToString(match)
        val deserialized = json.decodeFromString<FileMatch>(serialized)

        assertEquals("Main.kt", deserialized.name)
        assertEquals("src/main/kotlin/Main.kt", deserialized.path)
        assertEquals("src/main/kotlin", deserialized.directory)
    }

    fun testFileMatchRootDirectory() {
        val match = FileMatch(
            name = "README.md",
            path = "README.md",
            directory = ""
        )

        val serialized = json.encodeToString(match)
        val deserialized = json.decodeFromString<FileMatch>(serialized)

        assertEquals("README.md", deserialized.name)
        assertEquals("README.md", deserialized.path)
        assertEquals("", deserialized.directory)
    }

    // SearchTextResult tests

    fun testSearchTextResultSerialization() {
        val result = SearchTextResult(
            matches = listOf(
                TextMatch("src/Main.kt", 10, 5, "val config = ConfigManager()", "CODE"),
                TextMatch("src/Service.kt", 25, 12, "// TODO: refactor this", "COMMENT")
            ),
            totalCollected = 2,
            query = "config"
        )

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<SearchTextResult>(serialized)

        assertEquals(2, deserialized.matches.size)
        assertEquals(2, deserialized.totalCollected)
        assertEquals("config", deserialized.query)
        assertEquals("src/Main.kt", deserialized.matches[0].file)
    }

    fun testSearchTextResultEmpty() {
        val result = SearchTextResult(matches = emptyList(), totalCollected = 0, query = "NonExistentTerm")

        val serialized = json.encodeToString(result)
        val deserialized = json.decodeFromString<SearchTextResult>(serialized)

        assertTrue(deserialized.matches.isEmpty())
        assertEquals(0, deserialized.totalCollected)
    }

    // TextMatch tests

    fun testTextMatchSerialization() {
        val match = TextMatch(
            file = "src/Processor.kt",
            line = 50,
            column = 15,
            context = "val result = processor.process(data)",
            contextType = "CODE"
        )

        val serialized = json.encodeToString(match)
        val deserialized = json.decodeFromString<TextMatch>(serialized)

        assertEquals("src/Processor.kt", deserialized.file)
        assertEquals(50, deserialized.line)
        assertEquals(15, deserialized.column)
        assertEquals("val result = processor.process(data)", deserialized.context)
        assertEquals("CODE", deserialized.contextType)
    }

    fun testTextMatchAllContextTypes() {
        val contextTypes = listOf("CODE", "COMMENT", "STRING_LITERAL")

        contextTypes.forEach { contextType ->
            val match = TextMatch("file.kt", 1, 1, "test context", contextType)
            val serialized = json.encodeToString(match)
            val deserialized = json.decodeFromString<TextMatch>(serialized)
            assertEquals(contextType, deserialized.contextType)
        }
    }

    fun testImplementationLocationCarriesQualifiedName() {
        val loc = ImplementationLocation(
            name = "Anonymous in Foo.bar()",
            file = "src/Foo.java",
            line = 10,
            column = 4,
            kind = "CLASS",
            qualifiedName = "com.example.Foo\$1"
        )
        val serialized = json.encodeToString(loc)
        val deserialized = json.decodeFromString<ImplementationLocation>(serialized)
        assertEquals("com.example.Foo\$1", deserialized.qualifiedName)
    }

    fun testImplementationLocationOmittedQualifiedNameDefaultsToNull() {
        val loc = ImplementationLocation(
            name = "Foo",
            file = "Foo.java",
            line = 1,
            column = 1,
            kind = "CLASS"
        )
        assertNull(loc.qualifiedName)
    }

    fun testTypeElementCarriesQualifiedName() {
        val el = TypeElement(
            name = "Foo",
            qualifiedName = "com.example.Foo",
            kind = "CLASS",
            file = "Foo.java",
            line = 1,
            column = 7
        )
        val serialized = json.encodeToString(el)
        val deserialized = json.decodeFromString<TypeElement>(serialized)
        assertEquals("com.example.Foo", deserialized.qualifiedName)
    }

    fun testTypeElementCarriesEnclosingScope() {
        val el = TypeElement(
            name = "Comparator",
            enclosingScope = listOf("UserService", "sortByName"),
            kind = "CLASS",
            file = "src/UserService.java",
            line = 64,
            column = 35
        )
        val serialized = json.encodeToString(el)
        val deserialized = json.decodeFromString<TypeElement>(serialized)
        assertNull(deserialized.qualifiedName)
        assertEquals(listOf("UserService", "sortByName"), deserialized.enclosingScope)
    }

    fun testCallElementCarriesQualifiedName() {
        val el = CallElement(
            name = "bar",
            qualifiedName = "com.example.Foo#bar()",
            kind = "METHOD",
            file = "Foo.java",
            line = 5,
            column = 2
        )
        val serialized = json.encodeToString(el)
        val deserialized = json.decodeFromString<CallElement>(serialized)
        assertEquals("com.example.Foo#bar()", deserialized.qualifiedName)
    }

    fun testCallElementCarriesEnclosingScope() {
        val el = CallElement(
            name = "lambda$0",
            enclosingScope = listOf("UserService", "filterBy"),
            kind = "FUNCTION",
            file = "src/UserService.java",
            line = 42,
            column = 18
        )
        val serialized = json.encodeToString(el)
        val deserialized = json.decodeFromString<CallElement>(serialized)
        assertNull(deserialized.qualifiedName)
        assertEquals(listOf("UserService", "filterBy"), deserialized.enclosingScope)
    }

    // #30 — paginated results must not emit the misleading `totalCount` alias; completeness is
    // signalled by hasMore/nextCursor and the collected count carried by `totalCollected`.

    fun testPaginatedResultsDoNotEmitTotalCount() {
        val objects = listOf(
            "find_usages" to json.encodeToJsonElement(
                FindUsagesResult(usages = emptyList(), totalCollected = 7, hasMore = true)
            ).jsonObject,
            "find_implementations" to json.encodeToJsonElement(
                ImplementationResult(implementations = emptyList(), totalCollected = 7, hasMore = true)
            ).jsonObject,
            "find_symbol" to json.encodeToJsonElement(
                FindSymbolResult(symbols = emptyList(), query = "q", totalCollected = 7, hasMore = true)
            ).jsonObject,
            "find_class" to json.encodeToJsonElement(
                FindClassResult(classes = emptyList(), query = "q", totalCollected = 7, hasMore = true)
            ).jsonObject,
            "find_file" to json.encodeToJsonElement(
                FindFileResult(files = emptyList(), query = "q", totalCollected = 7, hasMore = true)
            ).jsonObject,
            "search_text" to json.encodeToJsonElement(
                SearchTextResult(matches = emptyList(), query = "q", totalCollected = 7, hasMore = true)
            ).jsonObject,
        )

        for ((tool, obj) in objects) {
            assertFalse("$tool must not emit totalCount", obj.containsKey("totalCount"))
            assertTrue("$tool must keep totalCollected", obj.containsKey("totalCollected"))
            assertEquals("$tool totalCollected", 7, obj["totalCollected"]!!.jsonPrimitive.int)
            assertTrue("$tool must keep hasMore for pagination", obj["hasMore"]!!.jsonPrimitive.content.toBoolean())
        }
    }
}
