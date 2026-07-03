package com.github.vcth4nh.idesense.util

object PluginDetectors {
    val php = PluginDetector(
        name = "PHP",
        pluginIds = listOf("com.jetbrains.php")
    )

    val rust = PluginDetector(
        name = "Rust",
        pluginIds = listOf("com.jetbrains.rust"),
        fallbackClass = "org.rust.lang.core.psi.RsFile"
    )
}
