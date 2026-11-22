#!/usr/bin/env bash
# Prepare the jitsi-videobridge checkout for IntelliJ IDEA. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../jitsi-videobridge" && pwd)
# The modules compile for Java 17 (maven-compiler-plugin source and target 17, Kotlin
# jvmTarget 17). Maven runs on a JDK 17 that mise installs in the user scope; this script sets
# no global version.
if ! command -v mise >/dev/null; then
  echo "jitsi-videobridge needs mise for its JDK 17 (https://mise.jdx.dev)" >&2; exit 1
fi
jdk_version=temurin-17.0.21.1+2
mise install -q "java@$jdk_version"
jdk=$(mise where "java@$jdk_version")
# Maven: `mvn` from the PATH, else the newest Maven 3.9 that the Maven Wrapper has downloaded.
mvn=$(command -v mvn || ls -d "$HOME"/.m2/wrapper/dists/apache-maven-3.9.*/*/bin/mvn 2>/dev/null | sort -V | tail -1 || true)
if [ -z "$mvn" ]; then
  echo "jitsi-videobridge needs Maven 3.9 or later: put mvn on the PATH (https://maven.apache.org/download.cgi)" >&2; exit 1
fi
version=$(JAVA_HOME="$jdk" "$mvn" -v)
need=3.9.0
have=$(sed -n 's/^Apache Maven \([0-9.]*\).*/\1/p' <<<"$version")
if [ "$(printf '%s\n%s\n' "$need" "$have" | sort -V | head -1)" != "$need" ]; then
  echo "jitsi-videobridge needs Maven $need or later, found $have ($mvn)" >&2; exit 1
fi
if ! grep -q '^Java version: 17\.' <<<"$version"; then
  echo "jitsi-videobridge needs a JDK 17 for Maven, found $jdk" >&2; exit 1
fi
# The POMs pin each dependency version and each plugin version, and no POM has a version
# range, so there is no lockfile to create. go-offline gets the dependencies and plugins of
# the three modules from Maven Central and from the GitHub-hosted jitsi-maven-repository
# (jitsi-dcsctp). It leaves out the modules of the reactor. The product has no code
# generation step: each source file is tracked.
(cd "$product" && JAVA_HOME="$jdk" "$mvn" -B -ntp -q dependency:go-offline)
# IntelliJ downloads the sources jars of the libraries after each Maven sync (Maven setting
# "Automatically download: Sources", on by default). Until then a definition into a library
# gives the .class file, after it the source file. So get now the sources jars of the
# libraries that the expected definition rows name. dependency:get resolves one artifact and
# no module of the product. It runs outside the checkout, so Maven reads no POM of the
# product; jitsi-dcsctp is only in the jitsi-maven-repository.
pom_property() { sed -n "s:.*<$1>\(.*\)</$1>.*:\1:p" "$product/pom.xml"; }
dcsctp=$(grep -A1 '<artifactId>jitsi-dcsctp</artifactId>' "$product/jvb/pom.xml" | sed -n 's:.*<version>\(.*\)</version>.*:\1:p')
jitsi_repo=https://github.com/jitsi/jitsi-maven-repository/raw/master/releases/
for artifact in "com.fasterxml.jackson.core:jackson-databind:$(pom_property jackson.version)" \
    "org.jitsi:jitsi-utils:$(pom_property jitsi.utils.version)" "org.jitsi:jitsi-dcsctp:$dcsctp"; do
  (cd "$here" && JAVA_HOME="$jdk" "$mvn" -B -ntp -q dependency:get -Dtransitive=false \
    "-DremoteRepositories=jitsi::default::$jitsi_repo" -Dartifact="$artifact:jar:sources")
done
# IntelliJ makes the Maven model at the first open when misc.xml names the root POM. The
# module files go to the system folder of the IDE, not into the checkout. The project SDK is
# the IDE JDK with the name 21: IntelliJ wrote these three components at a first open of a
# copy with no .idea. The checkout tracks no file in .idea, and its .gitignore ignores .idea
# and *.iml.
idea="$product/.idea"
mkdir -p "$idea"
if [ ! -f "$idea/misc.xml" ]; then
  cat > "$idea/misc.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="ExternalStorageConfigurationManager" enabled="true" />
  <component name="MavenProjectsManager">
    <option name="originalFiles">
      <list>
        <option value="$PROJECT_DIR$/pom.xml" />
      </list>
    </option>
  </component>
  <component name="ProjectRootManager" version="2" languageLevel="JDK_21" default="true" project-jdk-name="21" project-jdk-type="JavaSDK" />
</project>
XML
fi
if git -C "$product" status --porcelain --untracked-files=no | grep -q .; then
  echo "bootstrap changed a tracked file" >&2; exit 1
fi
echo "jitsi-videobridge: ready"
