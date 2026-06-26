package com.github.vcth4nh.idesense.testutil

import com.intellij.openapi.projectRoots.Sdk
import com.intellij.testFramework.IdeaTestUtil
import com.intellij.testFramework.LightProjectDescriptor
import com.intellij.testFramework.fixtures.DefaultLightProjectDescriptor

/**
 * `BasePlatformTestCase` defaults to `LightProjectDescriptor.EMPTY_PROJECT_DESCRIPTOR`,
 * which has no SDK. Tests that rely on `java.lang.*` resolution (anonymous Runnable,
 * `java.lang.Enum`, parameter types in `JavaQualifiedNameProvider` signatures) need a
 * mock JDK on the classpath.
 *
 * Override `getProjectDescriptor()` in the test class to return [JAVA_PROJECT_DESCRIPTOR].
 */
val JAVA_PROJECT_DESCRIPTOR: LightProjectDescriptor = object : DefaultLightProjectDescriptor() {
    override fun getSdk(): Sdk = IdeaTestUtil.getMockJdk21()
}
