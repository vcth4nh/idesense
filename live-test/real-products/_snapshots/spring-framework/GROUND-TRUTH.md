# Captured ground truth: spring-framework

These results look wrong, but the IDE returns the same. Do not change the probe to "fix" them.
The window observations used IntelliJ IDEA 2026.3 (IU-263.7307.200).

- **spring-framework: the Kotlin extension functions `getBean` and `getBeansOfType` have the
  `qualifiedName` null.** Rows: `def-getBean-kotlin-ext-from-kotlin`,
  `explain-getBean-kotlin-ext-pos`, `find-symbol-BeanFactory.getBean-qualified` (3 items),
  `find-symbol-getBean-lang-kotlin` (3 items), `find-symbol-getBeansOfType` (1 item). These are
  top-level `inline fun <reified T : Any>` extensions in `BeanFactoryExtensions.kt` and
  `ListableBeanFactoryExtensions.kt`. Copy Reference on `getBean` at
  `BeanFactoryExtensions.kt:29` gives the path and the line
  (`org/springframework/beans/factory/BeanFactoryExtensions.kt:29`), and no qualified name.
- **spring-framework: `usage-getBean-kotlin-ext` counts 42 usages, Find Usages shows 39.** The
  tool gives one entry for each usage. The Find Usages view joins the usages of one line into
  one node, and the 42 usages are on 39 lines.
- **spring-framework: `search-text-AnnotationTransactionAspect` has 19 matches, the source has
  20 occurrences.** The 20 occurrences are on 19 lines, and the tool keeps one match for each
  line (see "`ide_search_text`: one match for each line" in `docs/ARCHITECTURE.md`).
- **spring-framework: `find-symbol-getBean-lang-java` and `find-symbol-getBeansOfType` give no
  override.** Go to Symbol with `getBean` lists the 19 Java methods of the row. The observed
  part of the list (the first 30 items) has no `getBean` of `AbstractBeanFactory`,
  `StaticListableBeanFactory`, `DefaultListableBeanFactory` or `SimpleJndiBeanFactory`, which
  override `BeanFactory.getBean`. The Java contributor of Go to
  Symbol drops a Java method that has a super method (`DefaultSymbolNavigationContributor` calls
  `DefaultMethodNavigationContributor.hasSuperMethod`,
  `plugins/java/lib/modules/intellij.java.impl.jar`, build IU-263.7307.200). With the query
  `BeanFactory.getBean`, Go to Symbol lists these overrides too: its first 25 items are the 25
  of `find-symbol-BeanFactory.getBean-qualified`, and the next items have longer names. Go to
  Symbol with `getBeansOfType` was not observed.
- **spring-framework: `impls-ConfigurableApplicationContext.refresh` names the `refresh` of an
  anonymous class `org.springframework.context.support.ClassPathXmlApplicationContext#refresh`.**
  The method is in an anonymous subclass of `ClassPathXmlApplicationContext` in
  `ContextLoaderTests.java`, line 327. For a member of an anonymous class,
  `JavaQualifiedNameProvider.getMethodOrFieldQualifiedName` uses the base class type of the
  anonymous class (`plugins/java/lib/modules/intellij.java.impl.jar`, build IU-263.7307.200).
  Copy Reference on that method gives the same text. Go to Implementation on
  `ConfigurableApplicationContext.refresh` shows "4 found", as the row.
- **spring-framework: `hier-callee-AbstractApplicationContext.refresh-d1` lists 3 methods named
  `refresh` as callees.** The body of `refresh()` calls 24 methods. The 3 other entries are the
  methods that override `refresh()`, the same 3 as in
  `impls-ConfigurableApplicationContext.refresh`. The Callees view of the IDE adds them too:
  `CalleeMethodsTreeStructure.buildChildren` adds the result of
  `OverridingMethodsSearch.search(method, scope, true)` to the callees (bytecode offsets
  269-297, `plugins/java/lib/modules/intellij.java.impl.jar`, build IU-263.7307.200).
- **spring-framework: `usage-BeanPostProcessor-page1` and `-page2` count 157 usages, Find
  Usages also shows 4 non-code usages.** Find Usages shows "Usages in Project Files 157
  results" and a separate group "Non-code usages in Project Files 4 results". The tool searches
  no text occurrences (see the passes of `ide_find_usages` in `docs/ARCHITECTURE.md`).
- **spring-framework: the files below the tracked symbolic link
  `framework-docs/modules/ROOT/examples/docs-src` count two times in a text search, and
  `ide_search_text` drops one of them (#328).** The link goes to `framework-docs/src`. Find in
  Files with `BeanPostProcessor`, "Words" and "Match case" shows 260 results. It lists
  `MyPostProcessor.java` and `MyPostProcessor.kt` below `framework-docs/src`, and both files
  again below `docs-src`, with 2 results each. The tracked files have the word on 256 lines.
  `ide_search_text` gives 258: the Java file below `docs-src` is in the result, the Kotlin file
  below `docs-src` is not.
  - `ide_find_file` gives each file two times, one time below each path. With the scope
    `project_production_files`, each file name gives only the file below `framework-docs/src`.
    `MyPostProcessor.kt` with the scope `project_test_files` gives no file. So both files below
    the link are in the project and in no source root.
  - `ide_find_definition` on the supertype `BeanPostProcessor` gives "Could not resolve symbol
    definition" in both files below the link. In both files below `framework-docs/src` it gives
    `BeanPostProcessor.java`, line 67.
  - So only the text search separates the two files below the link. Not tested: a Kotlin file in
    no source root that is not below a link (the product tracks no such file). So the condition
    can be the link or the place outside the source roots.
  - `search-text-BeanPostProcessor-paged` is parked with #328. No other row depends on the link.
- **spring-framework: parked rows.** Each of these rows shows an open defect (see "Parked
  rows" in `live-test/CONVENTIONS.md`).
  - `impls-BeanPostProcessor` (#277): the tool gives 62 types. Go to Implementation shows "76
    found": also 13 Java anonymous classes and 1 Kotlin object expression in test sources.
  - `impls-HandlerMapping-webmvc` (#277): the tool gives 20 types. Go to Implementation shows
    "21 found": also the anonymous subclass of `AbstractUrlHandlerMapping` in the field
    `mapping` of `AbstractUrlHandlerMappingTests`.
  - `hier-sub-BeanPostProcessor-d20` (#304): the anonymous class at
    `GenericApplicationContextTests.java`, line 615, gets the `qualifiedName`
    `org.springframework.beans.factory.support.BeanDefinitionBuilder#setRole`, a method of
    another class. Go to Implementation shows it as "Anonymous in
    refreshForAotRegisterProxyHint() in GenericApplicationContextTests".
  - `hier-sub-ApplicationContext-d20` and `hier-sub-AbstractApplicationContext-d20` (#304): each
    tree has 8 Java anonymous classes and 1 local class (`TestContext`) in test sources. Each of
    these classes gets the method that holds it as `qualifiedName`, for example
    `org.springframework.context.event.PayloadApplicationEventTests#payloadObjectWithPayloadType`.
    The rows with the suffix `-production-scope` give the same two trees with the scope
    `production`. They have no anonymous class and no local class, and they are blessed.
  - `file-structure-AbstractApplicationContext.java` (#326): the tool gives the static
    initializer as `static static class initializer`. The Structure tool window shows
    `static class initializer`.
  - `search-text-BeanPostProcessor-paged` (#328): see the note on the symbolic link `docs-src`.
