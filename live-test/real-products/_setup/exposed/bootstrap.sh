#!/usr/bin/env bash
# Prepare the exposed checkout for IntelliJ IDEA. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../exposed" && pwd)
# Each module of the build sets jvmToolchain(17), and settings.gradle.kts has no toolchain
# resolver. Gradle finds no JDK that mise installed, except the JVM that runs Gradle. So
# Gradle runs on a JDK 17: then that JDK is the toolchain of each module. mise installs it in
# the user scope; this script sets no global version.
if ! command -v mise >/dev/null; then
  echo "exposed needs mise for its JDK 17 (https://mise.jdx.dev)" >&2; exit 1
fi
jdk_version=temurin-17.0.21.1+2
mise install -q "java@$jdk_version"
jdk=$(mise where "java@$jdk_version")
version=$("$jdk/bin/java" -version 2>&1)
if ! grep -q '^openjdk version "17\.' <<<"$version"; then
  echo "exposed needs a JDK 17, found $jdk" >&2; exit 1
fi
# The version catalog (gradle/libs.versions.toml) pins each dependency version, so there is
# no lockfile to create. The init script resolves the compile and runtime classpaths of each
# source set, which the Gradle sync of IntelliJ reads. --no-daemon and -Xmx1g: the build
# sets no heap limit, and Gradle leaves no daemon behind. In-process Kotlin compilation of
# buildSrc leaves no Kotlin daemon behind.
(cd "$product" && JAVA_HOME="$jdk" ./gradlew --no-daemon --no-configuration-cache -q \
  "-Dorg.gradle.jvmargs=-Xmx1g -Dfile.encoding=UTF-8" -Pkotlin.compiler.execution.strategy=in-process \
  -I "$here/resolve-dependencies.init.gradle" resolveDependenciesForIde)
# The Gradle JVM of IntelliJ: "#GRADLE_LOCAL_JAVA_HOME" in gradle.xml takes java.home of
# .gradle/config.properties (GradleLocalPropertiesFile, intellij.gradle.jar). This file
# follows the JDK path of this machine, so the script writes it each time.
mkdir -p "$product/.gradle"
printf 'java.home=%s\n' "$jdk" > "$product/.gradle/config.properties"
# gradle.xml links the root build (and not the separate builds in samples/ and
# documentation-website/). misc.xml keeps the module files in the system folder of the IDE
# (ExternalStorageConfigurationManager). The IDE adds the module list to gradle.xml after
# its first sync. The checkout tracks only four other files in .idea.
idea="$product/.idea"
if [ ! -f "$idea/gradle.xml" ]; then
  cat > "$idea/gradle.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="GradleMigrationSettings" migrationVersion="1" />
  <component name="GradleSettings">
    <option name="linkedExternalProjectsSettings">
      <GradleProjectSettings>
        <option name="externalProjectPath" value="$PROJECT_DIR$" />
        <option name="gradleJvm" value="#GRADLE_LOCAL_JAVA_HOME" />
        <option name="modules">
          <set>
            <option value="$PROJECT_DIR$" />
          </set>
        </option>
      </GradleProjectSettings>
    </option>
  </component>
</project>
XML
fi
if [ ! -f "$idea/misc.xml" ]; then
  cat > "$idea/misc.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="ExternalStorageConfigurationManager" enabled="true" />
</project>
XML
fi
if git -C "$product" status --porcelain --untracked-files=no | grep -q .; then
  echo "bootstrap changed a tracked file" >&2; exit 1
fi
echo "exposed: ready"
