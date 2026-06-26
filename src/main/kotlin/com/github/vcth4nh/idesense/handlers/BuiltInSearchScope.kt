package com.github.vcth4nh.idesense.handlers

enum class BuiltInSearchScope(val wireValue: String) {
    PROJECT_FILES("project_files"),
    PROJECT_AND_LIBRARIES("project_and_libraries"),
    PROJECT_PRODUCTION_FILES("project_production_files"),
    PROJECT_TEST_FILES("project_test_files");

    companion object {
        fun fromWireValue(value: String): BuiltInSearchScope? =
            values().firstOrNull { it.wireValue == value }

        fun supportedWireValues(): List<String> = values().map { it.wireValue }
    }
}
