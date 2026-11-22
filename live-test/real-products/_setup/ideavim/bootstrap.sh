#!/usr/bin/env bash
# Prepare the ideavim checkout for IntelliJ IDEA. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../ideavim" && pwd)
# gradle.properties sets javaVersion=21, and the root build.gradle.kts stops the build unless
# Gradle runs on a JDK 21. Each module sets a Java 21 toolchain, which is then that JVM. mise
# installs the JDK in the user scope; this script sets no global version.
if ! command -v mise >/dev/null; then
  echo "ideavim needs mise for its JDK 21 (https://mise.jdx.dev)" >&2; exit 1
fi
jdk_version=openjdk-21.0.2
mise install -q "java@$jdk_version"
jdk=$(mise where "java@$jdk_version")
version=$("$jdk/bin/java" -version 2>&1)
if ! grep -q '^openjdk version "21\.' <<<"$version"; then
  echo "ideavim needs a JDK 21, found $jdk" >&2; exit 1
fi
# The init script resolves the external modules of the classpaths that the Gradle sync of
# IntelliJ reads. The IntelliJ Platform Gradle Plugin then downloads IntelliJ IDEA 2026.1 two
# times and extracts both: the installer (twelve projects) and the Maven archive
# (tests/long-running-tests and tests/property-tests set useInstaller = false).
# :vim-engine:generateGrammarSource generates the ANTLR parsers into vim-engine/build, a source
# root of the module. No KSP task runs: KSP writes tracked files in ksp-generated/.
# --no-daemon and -Xmx2g: gradle.properties sets no heap limit, and Gradle leaves no daemon
# behind. --no-configuration-cache: the init script adds tasks.
# After an open, the IDE can have changed .idea/misc.xml (ideOwnedFiles in products.json). So
# the check compares the tracked files before the Gradle run with the tracked files after it.
tracked_state() {
  git -C "$product" status --porcelain --untracked-files=no
  git -C "$product" diff --no-ext-diff
}
before=$(tracked_state)
(cd "$product" && JAVA_HOME="$jdk" ./gradlew --no-daemon --no-configuration-cache -q \
  "-Dorg.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8" \
  -I "$here/resolve-dependencies.init.gradle" resolveDependenciesForIde :vim-engine:generateGrammarSource)
if [ "$(tracked_state)" != "$before" ]; then
  echo "bootstrap changed a tracked file" >&2; exit 1
fi
# The tracked .idea/gradle.xml sets the Gradle JVM "jbr-21". IntelliJ IDEA finds a JetBrains
# Runtime 21 in ~/.jdks and adds it with that name. With no such JDK it asks in a dialog to
# download one, and it keeps the name empty in gradle.xml until the download ends (see notes.md).
if ! compgen -G "$HOME/.jdks/jbr-21*" >/dev/null; then
  echo "ideavim needs a JetBrains Runtime 21 in a folder ~/.jdks/jbr-21* (for example" \
    "~/.jdks/jbr-21.0.11). IntelliJ IDEA installs one there: open the checkout in an IDE with a" \
    "window (not the fleet IDE) and click Download in its dialog 'Download SDK? ... wants to" \
    "download JetBrains Runtime 21'." >&2; exit 1
fi
echo "ideavim: ready"
