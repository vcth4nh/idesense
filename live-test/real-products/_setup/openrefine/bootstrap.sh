#!/usr/bin/env bash
# Prepare the openrefine checkout for IntelliJ IDEA. Idempotent. Changes no tracked file.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
product=$(cd "$here/../../openrefine" && pwd)
# Maven: `mvn` from the PATH, else the newest Maven 3.9 that the Maven Wrapper has downloaded.
mvn=$(command -v mvn || ls -d "$HOME"/.m2/wrapper/dists/apache-maven-3.9.*/*/bin/mvn 2>/dev/null | sort -V | tail -1 || true)
if [ -z "$mvn" ]; then
  echo "openrefine needs Maven 3.9 or later: put mvn on the PATH (https://maven.apache.org/download.cgi)" >&2; exit 1
fi
version=$("$mvn" -v)
need=3.9.0
have=$(sed -n 's/^Apache Maven \([0-9.]*\).*/\1/p' <<<"$version")
if [ "$(printf '%s\n%s\n' "$need" "$have" | sort -V | head -1)" != "$need" ]; then
  echo "openrefine needs Maven $need or later, found $have ($mvn)" >&2; exit 1
fi
# The POM builds for Java 11 to 21 (java.minversion, java.maxversion).
jdk=$(sed -n 's/^Java version: \([0-9]*\).*/\1/p' <<<"$version")
if [ "$jdk" -lt 11 ] || [ "$jdk" -gt 21 ]; then
  echo "openrefine needs a JDK 11 to 21 for Maven, found $jdk: set JAVA_HOME" >&2; exit 1
fi
# The POMs pin every dependency version, so there is no lockfile. go-offline gets the
# dependencies and plugins of all modules. generate-sources runs the localizer plugin: it
# writes Java classes such as FunctionDescription into target/generated-sources, and about
# 300 source files use them. The build stops before process-sources, where a plugin sorts
# the imports of the sources.
(cd "$product" && "$mvn" -B -ntp -q dependency:go-offline generate-sources)
# IntelliJ downloads the sources jars of the libraries after each Maven sync (Maven setting
# "Automatically download: Sources", on by default). Until then a definition into a library
# gives the .class file, after it the .java file. The expected rows name jackson-databind
# only, so get its sources jar now. dependency:get resolves this one artifact and no module
# of the product. It runs outside the checkout, so Maven reads no POM of the product.
jackson=$(sed -n 's:.*<jackson.version>\(.*\)</jackson.version>.*:\1:p' "$product/pom.xml")
(cd "$here" && "$mvn" -B -ntp -q dependency:get -Dtransitive=false \
  -Dartifact="com.fasterxml.jackson.core:jackson-databind:$jackson:jar:sources")
# IntelliJ makes the Maven model at the first open when misc.xml names the root POM. The
# module files go to the system folder of the IDE, not into the checkout. The project SDK
# is the IDE JDK with the name 21. The checkout tracks only .idea/codeStyles.
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
  <component name="ProjectRootManager" version="2" project-jdk-name="21" project-jdk-type="JavaSDK" />
</project>
XML
fi
if git -C "$product" status --porcelain --untracked-files=no | grep -q .; then
  echo "bootstrap changed a tracked file" >&2; exit 1
fi
echo "openrefine: ready"
