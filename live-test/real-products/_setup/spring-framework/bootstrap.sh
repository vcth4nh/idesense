#!/usr/bin/env bash
# Prepare the spring-framework checkout for IntelliJ IDEA. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../spring-framework" && pwd)
# buildSrc/.../JavaConventions.java sets the Java toolchain 25 for each project (the release is
# 17), and settings.gradle has no toolchain resolver. Gradle finds no JDK that mise installed,
# except the JVM that runs Gradle. So Gradle runs on a JDK 25: then that JDK is the toolchain.
# mise installs it in the user scope; this script sets no global version.
if ! command -v mise >/dev/null; then
  echo "spring-framework needs mise for its JDK 25 (https://mise.jdx.dev)" >&2; exit 1
fi
jdk_version=openjdk-25.0.2
mise install -q "java@$jdk_version"
jdk=$(mise where "java@$jdk_version")
version=$("$jdk/bin/java" -version 2>&1)
if ! grep -q '^openjdk version "25\.' <<<"$version"; then
  echo "spring-framework needs a JDK 25, found $jdk" >&2; exit 1
fi
tracked_state() {
  git -C "$product" status --porcelain --untracked-files=no
  git -C "$product" diff --no-ext-diff
}
before=$(tracked_state)
# The init script resolves the external modules of the classpaths that the Gradle sync of
# IntelliJ reads, and lists them. spring-core uses the jars of :spring-core:javapoetRepackJar
# and :spring-core:objenesisRepackJar as api(files(...)) dependencies: without them the IDE
# cannot resolve the packages org.springframework.javapoet and org.springframework.objenesis.
# :spring-oxm:xjc generates the JAXB classes of the spring-oxm tests into a test source root.
# --no-scan and --no-build-cache: the build publishes no build scan and reads no remote cache.
# --no-daemon and -Xmx2g (gradle.properties sets -Xmx2048m): Gradle leaves no daemon behind.
# --no-configuration-cache: the init script adds tasks.
modules=$(mktemp -d)
trap 'rm -rf "$modules"' EXIT
(cd "$product" && JAVA_HOME="$jdk" ./gradlew --no-daemon --no-configuration-cache \
  --no-build-cache --no-scan --max-workers=4 -q \
  "-Dorg.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8" \
  -I "$here/resolve-dependencies.init.gradle" "-PresolvedModulesDir=$modules" \
  resolveDependenciesForIde :spring-core:javapoetRepackJar :spring-core:objenesisRepackJar \
  :spring-oxm:xjc)
if [ "$(tracked_state)" != "$before" ]; then
  echo "bootstrap changed a tracked file" >&2; exit 1
fi
# The build pins each version in framework-platform and has no lockfile. dependencies.lock
# holds the modules of the first run; a later run that resolves another set stops.
cat "$modules"/*.txt | sort -u > "$modules/all"
if [ ! -f "$here/dependencies.lock" ]; then
  cp "$modules/all" "$here/dependencies.lock"
elif ! diff -u "$here/dependencies.lock" "$modules/all" >&2; then
  echo "the resolved modules differ from dependencies.lock" >&2; exit 1
fi
# The Gradle JVM of IntelliJ: "#GRADLE_LOCAL_JAVA_HOME" in gradle.xml takes java.home of
# .gradle/config.properties (GradleLocalPropertiesFile, intellij.gradle.jar). This file
# follows the JDK path of this machine, so the script writes it each time.
mkdir -p "$product/.gradle"
printf 'java.home=%s\n' "$jdk" > "$product/.gradle/config.properties"
# gradle.xml links the root build. misc.xml keeps the module files in the system folder of the
# IDE (ExternalStorageConfigurationManager). The checkout tracks only .idea/icon.svg, and its
# .gitignore ignores the rest of .idea and .gradle.
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
if [ "$(tracked_state)" != "$before" ]; then
  echo "bootstrap changed a tracked file" >&2; exit 1
fi
echo "spring-framework: ready"
