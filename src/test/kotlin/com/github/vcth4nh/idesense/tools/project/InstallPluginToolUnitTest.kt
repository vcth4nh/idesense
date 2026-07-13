package com.github.vcth4nh.idesense.tools.project

import junit.framework.TestCase
import java.io.File
import java.nio.file.Files

class InstallPluginToolUnitTest : TestCase() {

    private lateinit var root: File

    override fun setUp() {
        super.setUp()
        root = Files.createTempDirectory("idesense-install-root").toFile()
    }

    override fun tearDown() {
        root.deleteRecursively()
        super.tearDown()
    }

    private fun roots() = listOf(root.path)

    private fun tempDirOutsideRoot(prefix: String): File =
        Files.createTempDirectory(prefix).toFile()

    fun testAbsolutePathInsideRootResolves() {
        val zip = File(root, "build/distributions/plugin.zip")
        zip.parentFile.mkdirs()
        zip.writeText("zip")

        assertEquals(
            zip.canonicalFile,
            InstallPluginTool.resolveWithinProjectRoots(roots(), zip.absolutePath)
        )
    }

    fun testRelativePathInsideRootResolves() {
        val zip = File(root, "build/distributions/plugin.zip")
        zip.parentFile.mkdirs()
        zip.writeText("zip")

        assertEquals(
            zip.canonicalFile,
            InstallPluginTool.resolveWithinProjectRoots(roots(), "build/distributions/plugin.zip")
        )
    }

    fun testAbsolutePathOutsideRootIsRejected() {
        val outside = tempDirOutsideRoot("idesense-outside")
        try {
            val zip = File(outside, "evil.zip")
            zip.writeText("zip")

            assertNull(InstallPluginTool.resolveWithinProjectRoots(roots(), zip.absolutePath))
        } finally {
            outside.deleteRecursively()
        }
    }

    fun testRelativeTraversalEscapingRootIsRejected() {
        assertNull(InstallPluginTool.resolveWithinProjectRoots(roots(), "../evil.zip"))
    }

    fun testSiblingDirectoryPrefixCollisionIsRejected() {
        val sibling = File(root.parentFile, root.name + "-evil")
        sibling.mkdirs()
        try {
            val zip = File(sibling, "plugin.zip")
            zip.writeText("zip")

            assertNull(InstallPluginTool.resolveWithinProjectRoots(roots(), zip.absolutePath))
        } finally {
            sibling.deleteRecursively()
        }
    }

    fun testSymlinkEscapingRootIsRejected() {
        val outside = tempDirOutsideRoot("idesense-link-target")
        try {
            val target = File(outside, "real.zip")
            target.writeText("zip")
            val link = File(root, "link.zip")
            Files.createSymbolicLink(link.toPath(), target.toPath())

            assertNull(InstallPluginTool.resolveWithinProjectRoots(roots(), link.absolutePath))
        } finally {
            outside.deleteRecursively()
        }
    }

    fun testPathInsideSecondRootResolves() {
        val second = tempDirOutsideRoot("idesense-second-root")
        try {
            val zip = File(second, "plugin.zip")
            zip.writeText("zip")

            assertEquals(
                zip.canonicalFile,
                InstallPluginTool.resolveWithinProjectRoots(
                    listOf(root.path, second.path),
                    zip.absolutePath
                )
            )
        } finally {
            second.deleteRecursively()
        }
    }

    fun testNoRootsRejectsExplicitPath() {
        val zip = File(root, "plugin.zip")
        zip.writeText("zip")

        assertNull(InstallPluginTool.resolveWithinProjectRoots(emptyList(), zip.absolutePath))
    }
}
