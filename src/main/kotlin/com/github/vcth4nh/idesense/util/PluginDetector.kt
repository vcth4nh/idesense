package com.github.vcth4nh.idesense.util

import com.github.vcth4nh.idesense.handlers.LanguageKindResolver
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.extensions.ExtensionPointName
import com.intellij.util.KeyedLazyInstance

/**
 * Tells if the plugin of a language is installed and enabled. The optional config file of that
 * plugin (`php-features.xml`, `rust-features.xml`) registers a [LanguageKindResolver] for
 * [language], and the platform loads an optional config file only when its plugin is installed
 * and enabled. The check reads the language attribute of each registered bean, so it loads no
 * class of the language plugin.
 */
class PluginDetector(
    val name: String,
    private val language: String,
) {
    private val log = logger<PluginDetector>()

    val isAvailable: Boolean by lazy { checkAvailable() }

    inline fun <T> ifAvailable(action: () -> T): T? =
        if (isAvailable) action() else null

    inline fun <T> ifAvailableOrElse(default: T, action: () -> T): T =
        if (isAvailable) action() else default

    private fun checkAvailable(): Boolean {
        if (KIND_RESOLVERS.extensionList.any { it.key == language }) {
            log.info("$name plugin detected via its languageKindResolver ($language)")
            return true
        }
        log.info("$name plugin not available — $name-specific features will be disabled")
        return false
    }

    private companion object {
        val KIND_RESOLVERS =
            ExtensionPointName.create<KeyedLazyInstance<LanguageKindResolver>>(LanguageKindResolver.EP_NAME_STRING)
    }
}
