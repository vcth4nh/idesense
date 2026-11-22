# Captured ground truth: jitsi-videobridge

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.
The window observations used IntelliJ IDEA 2026.3 (IU-263.7307.200).

- **jitsi-videobridge: `usage-PacketInfo-page1` counts 460 usages, Find Usages shows 457.**
  The tool gives one entry for each usage. The Find Usages view joins the usages of one line
  into one node: grouped by module only, it shows 424 results (303 in `jitsi-media-transform`,
  121 in `jitsi-videobridge`), and the 460 usages of the tool are on 424 lines, 303 and 121 per
  module. Grouped by usage type, it shows 457, because it joins only the usages of one line with
  the same usage type. The 16 comment usages are the KDoc links `[PacketInfo]`; a plain-text
  mention in a comment is no usage, in the tool and in the view.
- **jitsi-videobridge: `usage-Endpoint.wants-base-java` has 5 usages, Find Usages shows 4.**
  `Endpoint.wants` (Kotlin) overrides `PotentialPacketHandler.wants` (Java). The tool also
  searches the base method and marks such usages BASE (see "Where a tool differs from the IDE
  on purpose" in `docs/ARCHITECTURE.md`). The fifth usage is `relay.wants(...)` in
  `Conference.java`, a call through `Relay`, with the mark BASE.
- **jitsi-videobridge: `find-symbol-rewriteRtp` gives 11 of the 13 declarations.** Go to
  Symbol shows the same 11. The Java contributor of Go to Symbol drops a Java method that has a
  super method (`DefaultSymbolNavigationContributor` calls
  `DefaultMethodNavigationContributor.hasSuperMethod`, `plugins/java/lib/modules/intellij.java.impl.jar`,
  build IU-263.7307.200). So the two Java overrides are missing, and the Kotlin overrides stay.
  `find-symbol-rewriteRtp-lang-java` has 3 items and `-lang-kotlin` has 8.
- **jitsi-videobridge: in `hier-caller-AbstractEndpointMessageTransport.onMessage-d2`, the two
  Java nodes `EndpointMessageTransport.onDataChannelMessage` and `.webSocketTextReceived` have
  no children.** The Callers view shows no child under `onDataChannelMessage` either. These
  methods implement listener interfaces, and their callers call the interface method. As the
  root of a call hierarchy, each of them has one caller (`onIncomingMsg`, `onWebSocketText`).
  The Kotlin nodes `RelayMessageTransport.*` have one child each.
- **jitsi-videobridge: `hier-caller-ByteBufferPool.returnBuffer-production-scope` names a
  caller `org.ice4j.util.BufferHandler#handleBuffer`.** The caller is `handleBuffer` of an
  object expression in `IceTransport.kt`. The tool takes the qualified name from the
  `QualifiedNameProvider` of the IDE. For a member of an anonymous class,
  `JavaQualifiedNameProvider.getMethodOrFieldQualifiedName` uses the base class type of the
  anonymous class (`plugins/java/lib/modules/intellij.java.impl.jar`, build IU-263.7307.200).
  The name is the name of the library method that the object expression implements.
- **jitsi-videobridge: `search-text-drain` has 19 matches, Find in Files has 27.** The tool is
  case-sensitive by default (`caseSensitive: true`). Find in Files with "Words" on and "Match
  case" off shows 27 matches in 10 files; the 8 more matches are `Drain` and `DRAIN`. The
  default is an open decision in #219.
- **jitsi-videobridge: `super-DataChannelPacket.clone-kotlin` has two super methods.** The tool
  gives `Packet.clone` (Kotlin) and `Object.clone`: it gives all levels on purpose. Go to Super
  Method (Ctrl+U) goes to `Packet.clone` only, its direct super method.
- **jitsi-videobridge: `hier-callee-EndpointMessageTransport.webSocketTextReceived` was empty
  one time.** The first call after a project switch, during the Maven sync of the open, gave
  no callee. Each other run gave the 5 callees of the Callees view. The harness took the IDE as
  ready during the sync. See "The Maven project in IntelliJ" in
  `live-test/real-products/_setup/jitsi-videobridge/notes.md`.
- **jitsi-videobridge: parked rows.** Each of these rows shows an open defect (see "Parked
  rows" in `live-test/CONVENTIONS.md`).

  | Row | Issue | Defect |
  |---|---|---|
  | `impls-RtcpListener` | #277 | The tool gives the 7 named classes. Go to Implementation shows 10: also the 3 object expressions (Kotlin) in `Relay.kt`, `RelayEndpointSender.kt` and `RelayedEndpoint.kt` that implement the Java interface. |
  | `find-file-RtpPacket.kt-production-scope` | #271 | The tool gives 6 files. Go to File with the scope "Project Production Files" also lists files that match through the directory path, for example `RtcpFbPliPacket.kt`, `PaddingVideoPacket.kt` and `ParsedVideoPacket.kt`. |
