package com.github.vcth4nh.idesense.constants

/**
 * The marks of a usage that is not sure (#171), the field `match` of a usage. A sure usage has no mark.
 * - [BASE]: the usage refers to a base declaration of the symbol. The call can run the symbol or a
 *   different implementation.
 * - [DYNAMIC]: only the name matches. The type of the receiver is not known.
 */
object UsageMatch {
    const val BASE = "BASE"
    const val DYNAMIC = "DYNAMIC"
}
