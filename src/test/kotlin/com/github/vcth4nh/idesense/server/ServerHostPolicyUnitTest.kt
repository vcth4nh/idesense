package com.github.vcth4nh.idesense.server

import com.github.vcth4nh.idesense.McpConstants
import junit.framework.TestCase

class ServerHostPolicyUnitTest : TestCase() {

    fun testLoopbackHostsAreRecognized() {
        for (host in listOf("127.0.0.1", "localhost", "::1", "[::1]", "127.1.2.3", " LOCALHOST ")) {
            assertTrue("$host should be loopback", ServerHostPolicy.isLoopback(host))
        }
    }

    fun testNonLoopbackHostsAreRecognized() {
        for (host in listOf("0.0.0.0", "::", "192.168.1.5", "10.0.0.7", "example.com")) {
            assertFalse("$host should not be loopback", ServerHostPolicy.isLoopback(host))
        }
    }

    fun testLoopbackBindsWithoutAcknowledgement() {
        val resolution = ServerHostPolicy.resolve("127.0.0.1", acknowledged = false)

        assertEquals("127.0.0.1", resolution.effectiveHost)
        assertFalse("Loopback must never be blocked", resolution.blocked)
    }

    fun testNonLoopbackWithoutAcknowledgementFallsBackToLoopback() {
        val resolution = ServerHostPolicy.resolve("0.0.0.0", acknowledged = false)

        assertEquals(McpConstants.DEFAULT_SERVER_HOST, resolution.effectiveHost)
        assertTrue("Unacknowledged non-loopback bind must be blocked", resolution.blocked)
    }

    fun testNonLoopbackWithAcknowledgementBinds() {
        val resolution = ServerHostPolicy.resolve("0.0.0.0", acknowledged = true)

        assertEquals("0.0.0.0", resolution.effectiveHost)
        assertFalse("Acknowledged non-loopback bind is allowed", resolution.blocked)
    }

    fun testLanAddressWithoutAcknowledgementFallsBack() {
        val resolution = ServerHostPolicy.resolve("192.168.1.5", acknowledged = false)

        assertEquals(McpConstants.DEFAULT_SERVER_HOST, resolution.effectiveHost)
        assertTrue(resolution.blocked)
    }

    fun testAcknowledgementDoesNotChangeLoopbackHost() {
        val resolution = ServerHostPolicy.resolve("localhost", acknowledged = true)

        assertEquals("localhost", resolution.effectiveHost)
        assertFalse(resolution.blocked)
    }

    fun testBlankHostFallsBackToDefaultWithoutBlocking() {
        val resolution = ServerHostPolicy.resolve("   ", acknowledged = false)

        assertEquals(McpConstants.DEFAULT_SERVER_HOST, resolution.effectiveHost)
        assertFalse("Blank host is a config error, not an exposure", resolution.blocked)
    }

    fun testHostIsTrimmedBeforeBinding() {
        val resolution = ServerHostPolicy.resolve("  0.0.0.0  ", acknowledged = true)

        assertEquals("0.0.0.0", resolution.effectiveHost)
    }
}
