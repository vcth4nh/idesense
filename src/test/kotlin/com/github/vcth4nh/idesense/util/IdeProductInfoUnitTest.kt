package com.github.vcth4nh.idesense.util

import com.github.vcth4nh.idesense.util.IdeProductInfo.IdeProduct
import junit.framework.TestCase

// The product of an IDE for the product code of its build.
class IdeProductInfoUnitTest : TestCase() {

    // JetBrains discontinued Aqua (product code QA), so it has no entry (#241).
    fun testTheProductCodeOfAquaGivesUnknown() {
        assertEquals(IdeProduct.UNKNOWN, IdeProduct.fromProductCode("QA"))
    }
}
