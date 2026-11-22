# jitsi-videobridge

- Repository: https://github.com/jitsi/jitsi-videobridge
- Pin: tag `stable/jitsi-meet_11248`, commit `bf271b11f795d6546f8d78dee441c67d9ba2bf6b`,
  committed 2026-09-10
- License: Apache-2.0 (`LICENSE`)
- IDE: IntelliJ IDEA (port 29170)
- Build: Maven, a root POM and three modules (`rtp`, `jitsi-media-transform`, `jvb`). Kotlin
  2.2.20 (`kotlin.version`), Java and Kotlin target 17 (`source` and `target` of
  `maven-compiler-plugin`, `jvmTarget` of `kotlin-maven-plugin`).
- Languages: 484 Kotlin files (85,816 lines) and 80 Java files (18,503 lines), all in the
  three modules. Each module has Java and Kotlin in its production code. Two Java files are in
  a Kotlin source folder: `rtp/src/main/kotlin/org/jitsi/rtp/ByteArrayBufferImpl.java` and
  `jitsi-media-transform/src/main/kotlin/org/jitsi/nlj/rtcp/RtcpListener.java`.
- The two languages refer to each other in both directions. Examples: the Java class
  `DataChannelPacket` extends the Kotlin class `Packet`, which extends the Java class
  `ByteArrayBufferImpl`. The Java class `EndpointMessageTransport` extends the Kotlin class
  `AbstractEndpointMessageTransport`. The Kotlin classes `Endpoint` and `Relay` implement the
  Java interface `PotentialPacketHandler`.

## Setup

Run `bootstrap.sh`. It needs mise and Maven 3.9 or later. It installs the JDK
`temurin-17.0.21.1+2` with mise (user scope, no global version) and runs Maven on that JDK.
It takes `mvn` from the `PATH`, else the newest Maven 3.9 that the Maven Wrapper has put in
`~/.m2/wrapper/dists`. Then it runs `mvn dependency:go-offline`, gets three sources jars (see
below), and writes `.idea/misc.xml` when it is absent. There is no lockfile to create: the
POMs pin each dependency version and each plugin version, and no POM has a version range.
The root POM pins the versions of `jackson-bom` and `jitsi-utils` (properties
`jackson.version` and `jitsi.utils.version`), and `jvb/pom.xml` pins `jitsi-dcsctp`.

- Repositories. The three module POMs add the GitHub-hosted `jitsi-maven-repository`. Only
  `org.jitsi:jitsi-dcsctp` comes from it. The other `org.jitsi` libraries (for example
  `jitsi-utils`, `ice4j`, `jicoco-config`) come from Maven Central.
- No code generation. Each source file is tracked. `go-offline` leaves out the modules of the
  reactor, so Maven puts no jar of the product into `~/.m2`.
- `misc.xml` names the root POM in `MavenProjectsManager`. At the first open IntelliJ finds no
  Maven tree for this file and starts a full Maven sync. The module files go to the system
  folder of the IDE (`ExternalStorageConfigurationManager`), not into the checkout. The
  checkout tracks no file in `.idea`, and its `.gitignore` ignores `.idea` and `*.iml`.
- Project SDK. `misc.xml` names the IDE JDK `21` (`ProjectRootManager`, language level
  `JDK_21`). IntelliJ wrote the same three components when it opened a copy of the pin with no
  `.idea` folder (IDE 2026.3, a throwaway IDE with the fleet configuration).
- Library sources. After each Maven sync, IntelliJ downloads the sources jar of each library:
  the constructor of `MavenImportingSettings` sets `downloadSourcesAutomatically` to true
  (bytecode of `intellij.maven.jar`, IU-263.7307.200). Until a sources jar is there,
  `ide_find_definition` into that library gives the `.class` file, and after it the source
  file. So the bootstrap gets the sources jars of the three libraries that the definition rows
  name: `jackson-databind`, `jitsi-utils` and `jitsi-dcsctp`, with `dependency:get` outside
  the checkout.

Times on 2026-11-22: the first bootstrap run took 5 min 49 s (about 360 MB into `~/.m2`). The
first run of the sources step took 26 s. A later run takes 14 s.

## The Maven project in IntelliJ

- At each open, IntelliJ logs "MavenProjectsTree is inconsistent" and runs a full Maven sync
  (`updateAllMavenProjects incremental=false`, `MavenProjectsManager.onProjectStartup`). The
  model from the cache is there before the sync, and the canary rows resolve. The sync takes 7
  to 10 s after a project switch.
- The model survives a project switch of the harness: six switches (openrefine and back, 14:00
  to 14:18) gave the same model, with no repair step.
- After the first sync, IntelliJ downloaded the sources jars of 11 libraries by itself
  (13:46 to 13:49:50).
- Wait for the end of the Maven sync after an open. The harness takes the IDE as ready when
  `ide_index_status` gives `isDumbMode: false`, and that comes before the end of the sync. The
  sync ends with this line in `idea.log`:
  `WARN - #o.j.i.maven - updateAllMavenProjects finished: incremental=false, MavenProjectsManager.onProjectStartup jitsi-videobridge`.
  The first call after one switch came during the sync and gave an empty result:
  `hier-callee-EndpointMessageTransport.webSocketTextReceived` had no callee, and each later
  call had 5.
- Do not start the next switch while IntelliJ still indexes or syncs. A switch 7 s after the
  previous one stopped IntelliJ during indexing. IntelliJ then logged "Requesting index rebuild
  for: Stubs" and "IdIndex". After each later start, the scans found no file to index, and the
  class search gave no project class in each project of the IDE. A start with an empty `index`
  folder of the IDE system folder repaired it: IntelliJ indexed all files again.

## Measured

IntelliJ IDEA 2026.3 (IU-263.7307.200), `-Xmx2048m`, plugin 2.1.1-dev.31, 2026-11-22.

| Item | Value |
|---|---|
| First open: switch, then ready | 53 s, then 40 s |
| First Maven sync | 17 s (13:45:27 to 13:45:44) |
| First open to full smart mode, with the downloads of the sources jars | 5 min 36 s |
| First indexing of the product | 21,020 + 32,070 + 2,625 + 3,281 files in four passes |
| Switch to the product after the first open | 11 to 22 s, ready 0 s |
| Maven sync after a switch | 7 to 10 s |
| Java fixture rows while the product is open | 144 passed |
| Kotlin fixture rows while the product is open | 119 passed |
| Resident memory of IntelliJ, two fixtures, before the open | 3,006 MB |
| Resident memory of IntelliJ, two fixtures plus the product, after the open | 3,608 MB |
| Used heap after a full collection, after the open | 428 MB |
| Checkout after the bootstrap and the open | 69 MB |
| Product run, 74 rows | 5 to 25 s |
| Slowest first call of a row after a switch | 4.9 s (`hier-caller-AbstractEndpointMessageTransport.onMessage-d2`) |

The used heap stays far below 1200 MB (60% of the limit), so IntelliJ keeps `-Xmx2048m`.
