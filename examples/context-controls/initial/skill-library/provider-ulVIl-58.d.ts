import z from "@deepseek-ai/schemastery";
import { SkillCandidate, SkillDefinition, SkillLookupOptions, SkillProvider, SkillProviderControl, SkillProviderObservation } from "@deepseek-ai/dsh-skill";
//#region src/sources.d.ts
/**
 * Git skill sources: parse `owner/repo`-style specs, keep a shallow clone per
 * repository in a local cache, and record what was synced in a lock file.
 *
 * Network work happens only here. Discovery reads the cached checkout, so a
 * failed sync degrades to "yesterday's skills" instead of an empty catalog.
 *
 * @module
 */
/** One source as written in configuration or a sources file. */
interface SourceSpec {
  /** `owner/repo`, `owner/repo/sub/dir`, `github:owner/repo`, a git URL, a GitHub tree URL, or a local path. */
  readonly repo: string;
  /** Branch, tag, or commit SHA. Defaults to the repository's default branch. */
  readonly ref?: string;
  /** Sub-directory to scan inside the repository. */
  readonly path?: string;
  /** Precedence rank inside dsh (lower wins). */
  readonly rank?: number;
}
interface ResolvedSource extends SourceSpec {
  /** Stable repository identifier (`github.com/owner/repo`); shared by every ref. */
  readonly id: string;
  /** `id` plus the ref when one is set; keys the cache directory and lock entry. */
  readonly key: string;
  /** Clone URL handed to git. */
  readonly url: string;
  /** Absolute cache directory holding the checkout. */
  readonly dir: string;
  /** Absolute directory to scan (`dir` plus `path`). */
  readonly scanDir: string;
  /** Short display name (for example `anthropics/skills`). */
  readonly display: string;
}
type SyncStatus = 'cloned' | 'updated' | 'unchanged' | 'failed' | 'skipped';
interface SyncResult {
  readonly source: ResolvedSource;
  readonly status: SyncStatus;
  readonly sha?: string;
  readonly error?: string;
}
interface LockEntry {
  readonly url: string;
  readonly ref?: string;
  readonly sha: string;
  readonly syncedAt: string;
}
type LockFile = Record<string, LockEntry>;
/** Normalise a string or object spec into a resolved source. */
declare function resolveSource(input: string | SourceSpec, cacheDir: string): ResolvedSource;
interface SyncOptions {
  readonly force?: boolean;
  readonly timeoutMs?: number;
  readonly signal?: AbortSignal;
  readonly log?: (message: string) => void;
}
/** Whether a usable `git` executable is on PATH (memoised). */
declare function hasGit(): Promise<boolean>;
/** Clone or update one source into its cache directory. */
declare function syncSource(source: ResolvedSource, options?: SyncOptions): Promise<SyncResult>;
declare function readLock(path: string): Promise<LockFile>;
/** Read a `sources.json`; a missing file is an empty list, a malformed one throws. */
declare function readSourcesFile(path: string): Promise<SourceSpec[]>;
declare function writeSourcesFile(path: string, sources: readonly (string | SourceSpec)[]): Promise<void>;
/** Whether two specs point at the same repository (ignoring ref/path/rank). */
declare function sameRepository(left: string | SourceSpec, right: string | SourceSpec, cacheDir: string): boolean;
//#endregion
//#region src/config.d.ts
interface RankConfig {
  /** Skills found in another agent's project directory (`.claude/skills`, ...). */
  readonly project?: number;
  /** Skills found in another agent's user directory (`~/.codex/skills`, ...). */
  readonly user?: number;
  /** Skills found inside Claude Code plugin marketplaces. */
  readonly claudePlugins?: number;
  /** Default rank for git sources without an explicit `rank`. */
  readonly sources?: number;
}
interface CatalogConfig {
  /** Maximum skills this provider exposes to the model catalog; `0` means unlimited. Default 50. */
  readonly limit?: number;
  /** Skill names always kept in the model catalog. */
  readonly pin?: readonly string[];
  /** Skill names never shown to the model catalog (still user-invocable and searchable). */
  readonly hide?: readonly string[];
}
interface Config {
  /** Unique provider name on `ctx.skills`. */
  readonly providerName?: string;
  /** Scan the skill directories of other coding agents. */
  readonly agents?: boolean;
  /** Agent ids (see `AGENTS`) to leave out. */
  readonly excludeAgents?: readonly string[];
  /** Extra project-relative skill directories scanned like an agent's. */
  readonly extraProjectDirs?: readonly string[];
  /** Extra absolute (or `~/`) skill directories scanned like an agent's user root. */
  readonly extraUserDirs?: readonly string[];
  /** Scan Claude Code plugin marketplaces and installed plugin caches. */
  readonly claudePlugins?: boolean;
  /** Git repositories full of skills. */
  readonly sources?: readonly (string | SourceSpec)[];
  /** Also read `<dshHome>/skills-anywhere/sources.json` and `<project>/.dsh/skills-anywhere.json`. */
  readonly sourcesFiles?: boolean;
  /** Where git sources are checked out. Defaults to `<dshHome>/skills-anywhere/cache`. */
  readonly cacheDir?: string;
  /** dsh home. Defaults to `$DSH_HOME` or `~/.dsh`. */
  readonly dshHome?: string;
  /** Home directory used to expand `~` and locate agent roots. Defaults to the OS home. */
  readonly home?: string;
  /** Clone and refresh git sources at all. */
  readonly sync?: boolean;
  /** Refresh sources when the plugin starts. */
  readonly syncOnStart?: boolean;
  /** Interval between background refreshes; `0` disables the timer. */
  readonly syncIntervalMs?: number;
  /** Per-git-command timeout. */
  readonly syncTimeoutMs?: number;
  /** Directory depth walked inside sources and marketplaces. */
  readonly maxDepth?: number;
  /** Collapse symlinked and byte-identical duplicates. */
  readonly dedupe?: boolean;
  /** Repair recoverable frontmatter problems instead of skipping the skill. */
  readonly lenient?: boolean;
  /** Watch local roots and refresh the catalog on changes. */
  readonly watch?: boolean;
  /** Skill names to hide. */
  readonly excludeSkills?: readonly string[];
  readonly ranks?: RankConfig;
  /** Model-catalog budget: which skills are listed for the model versus reachable through `find_skills`. */
  readonly catalog?: CatalogConfig;
}
declare const DEFAULT_RANKS: {
  readonly project: 250;
  readonly user: 550;
  readonly claudePlugins: 580;
  readonly sources: 700;
};
declare const Config: z<Config>;
interface ResolvedConfig {
  readonly providerName: string;
  readonly agents: boolean;
  readonly excludeAgents: ReadonlySet<string>;
  readonly extraProjectDirs: readonly string[];
  readonly extraUserDirs: readonly string[];
  readonly claudePlugins: boolean;
  readonly sources: readonly (string | SourceSpec)[];
  readonly sourcesFiles: boolean;
  readonly cacheDir: string;
  readonly dshHome: string;
  readonly home: string;
  readonly sync: boolean;
  readonly syncOnStart: boolean;
  readonly syncIntervalMs: number;
  readonly syncTimeoutMs: number;
  readonly maxDepth: number;
  readonly dedupe: boolean;
  readonly lenient: boolean;
  readonly watch: boolean;
  readonly excludeSkills: readonly string[];
  readonly ranks: Required<RankConfig>;
  readonly catalog: {
    readonly limit: number;
    readonly pin: ReadonlySet<string>;
    readonly hide: ReadonlySet<string>;
  };
  /** `<dshHome>/skills-anywhere` */
  readonly stateDir: string;
  /** User-level sources file. */
  readonly userSourcesFile: string;
  /** Lock file recording synced commits. */
  readonly lockFile: string;
}
/** Apply defaults and resolve every path. */
declare function resolveConfig(config?: Config, env?: Record<string, string | undefined>): ResolvedConfig;
/** Project-level sources file for a project root. */
declare function projectSourcesFile(projectRoot: string): string;
//#endregion
//#region src/frontmatter.d.ts
interface SkillInvocation {
  readonly modelInvocable: boolean;
  readonly userInvocable: boolean;
}
interface ParsedSkill {
  readonly name: string;
  readonly description: string;
  readonly whenToUse?: string;
  readonly invocation: SkillInvocation;
  /** Spec fields and pass-through extras, ready for `SkillCandidate.metadata`. */
  readonly metadata: Record<string, unknown>;
  /** Markdown body with the frontmatter removed and surrounding whitespace trimmed. */
  readonly content: string;
  /** Repairs applied in lenient mode; empty when the file was spec-clean. */
  readonly warnings: readonly string[];
}
type ParseResult = {
  readonly ok: true;
  readonly skill: ParsedSkill;
} | {
  readonly ok: false;
  readonly reason: string;
};
interface ParseOptions {
  /** Name used when the frontmatter has none (usually the directory name). */
  readonly fallbackName: string;
  /** Repair recoverable problems instead of rejecting the file. Default `true`. */
  readonly lenient?: boolean;
}
/** Whether a string is a valid Agent Skills / dsh skill name. */
declare function isSkillName$1(name: string): boolean;
/**
 * Normalise an arbitrary string into a valid skill name, or `undefined` when
 * nothing usable remains (for example an empty or all-punctuation string).
 */
declare function normalizeSkillName(input: string): string | undefined;
/** Split a Markdown document into YAML frontmatter text and body. */
declare function splitFrontmatter(raw: string): {
  frontmatter: string;
  body: string;
} | undefined;
/** Parse one SKILL.md (or flat `<name>.md`) document. */
declare function parseSkillMarkdown(raw: string, options: ParseOptions): ParseResult;
//#endregion
//#region src/discover.d.ts
type OriginKind = 'agent' | 'claude-plugins' | 'source' | 'custom';
interface SkillOrigin {
  readonly kind: OriginKind;
  /** Agent id from the agents table, when `kind` is `agent`. */
  readonly agent?: string;
  /** `project` or `user` for agent and custom roots. */
  readonly scope?: 'project' | 'user';
  /** Git source display name (for example `anthropics/skills`), when `kind` is `source`. */
  readonly repo?: string;
  /** Claude Code marketplace and plugin names, when `kind` is `claude-plugins`. */
  readonly marketplace?: string;
  readonly plugin?: string;
}
interface SkillRoot {
  /** Absolute directory to scan. */
  readonly path: string;
  /** Project root this root belongs to (project-scope roots only). */
  readonly project?: string;
  /** `SkillSource` label reported to dsh. */
  readonly source: string;
  /** Lower ranks win duplicate names inside the dsh registry layer. */
  readonly rank: number;
  readonly mode: 'flat' | 'nested';
  /** Maximum directory depth below `path` for `nested` roots. */
  readonly maxDepth?: number;
  readonly origin: SkillOrigin;
  /** Short label for diagnostics (for example `claude-code (user)`). */
  readonly label: string;
}
interface DiscoveredSkill {
  readonly name: string;
  readonly description: string;
  readonly whenToUse?: string;
  readonly invocation: ParsedSkill['invocation'];
  readonly source: string;
  readonly rank: number;
  /** Absolute path of the Markdown file. */
  readonly path: string;
  /** Directory whose files the skill may reference. */
  readonly directory: string;
  readonly metadata: Record<string, unknown>;
  readonly origin: SkillOrigin;
  readonly root: SkillRoot;
  readonly contentHash: string;
  readonly warnings: readonly string[];
}
interface DroppedSkill {
  readonly skill: DiscoveredSkill;
  readonly winner: DiscoveredSkill;
  readonly reason: 'same-file' | 'same-content' | 'excluded';
}
interface InvalidSkill {
  readonly path: string;
  readonly root: SkillRoot;
  readonly reason: string;
}
interface RootReport {
  readonly root: SkillRoot;
  readonly exists: boolean;
  readonly count: number;
}
interface DiscoveryReport {
  readonly skills: readonly DiscoveredSkill[];
  readonly dropped: readonly DroppedSkill[];
  readonly invalid: readonly InvalidSkill[];
  readonly roots: readonly RootReport[];
  /** False when at least one root failed with a non-absence error. */
  readonly complete: boolean;
}
interface DiscoverOptions {
  /** Collapse identical files (symlinks) and identical content. Default `true`. */
  readonly dedupe?: boolean;
  /** Repair recoverable frontmatter problems. Default `true`. */
  readonly lenient?: boolean;
  /** Skill names to drop after discovery. */
  readonly excludeSkills?: readonly string[];
  readonly signal?: AbortSignal;
  readonly warn?: (message: string) => void;
}
/** Discover skills under every root, then deduplicate across roots. */
declare function discover(roots: readonly SkillRoot[], options?: DiscoverOptions): Promise<DiscoveryReport>;
/** Nearest ancestor of `cwd` containing `.git`, else `cwd` itself (the dsh rule). */
declare function findProjectRoot(cwd: string): Promise<string>;
//#endregion
//#region src/catalog.d.ts
/** Pure catalog selection, shared by the provider and the browser playground. */
type CatalogState = 'visible' | 'hidden' | 'disabled';
interface CatalogSkill {
  readonly name: string;
  readonly invocation: {
    readonly modelInvocable: boolean;
  };
}
interface CatalogSelection {
  readonly limit: number;
  readonly pin: ReadonlySet<string>;
  readonly hide: ReadonlySet<string>;
}
/** Author-disabled skills never count; pins precede the remaining eligible skills. */
declare function applyCatalogBudget(skills: readonly CatalogSkill[], catalog: CatalogSelection): Map<string, CatalogState>;
//#endregion
//#region src/web-protocol.d.ts
/**
 * Wire shapes shared by the host remote (`skills-anywhere/report`) and the
 * browser card. Plain JSON, no dsh imports, so the client bundle can import
 * the types without pulling in Node code.
 *
 * @module
 */
/** Why a skill is or is not in the model catalog. */
type SkillState = 'visible' | 'hidden' | 'disabled';
interface SkillView {
  readonly name: string;
  readonly description: string;
  /** `originLabel()` of the skill's origin. */
  readonly origin: string;
  /** `originGroup()` of the skill's origin. */
  readonly group: string;
  readonly path: string;
  readonly state: SkillState;
  /** The skill's own frontmatter disables model invocation. */
  readonly authorDisabled: boolean;
  /** Present when a name collision renamed the skill. */
  readonly renamedFrom?: string;
  readonly pinned: boolean;
  readonly hidden: boolean;
  /** Frontmatter repairs and other warnings recorded at discovery. */
  readonly warnings: readonly string[];
}
interface DroppedView {
  readonly name: string;
  readonly path: string;
  readonly reason: 'same-file' | 'same-content' | 'excluded';
  readonly winner: string;
}
interface RootView {
  readonly label: string;
  readonly path: string;
  readonly exists: boolean;
  readonly count: number;
}
interface ReportView {
  readonly skills: readonly SkillView[];
  readonly dropped: readonly DroppedView[];
  readonly invalid: readonly {
    readonly path: string;
    readonly reason: string;
  }[];
  readonly roots: readonly RootView[];
  readonly complete: boolean;
  /** Current runtime catalog settings, as the host resolved them. */
  readonly catalog: {
    readonly limit: number;
    readonly pin: readonly string[];
    readonly hide: readonly string[];
  };
  readonly excludeSkills: readonly string[];
  /** Number of skills the model catalog lists right now. */
  readonly listed: number;
}
/** Settings namespace the host registers and the card edits. */
declare const SETTINGS_NAMESPACE = "skills-anywhere";
/**
 * Exact Fetch route the host registers on the dsh connection's shared `/api`
 * channel (the public seam for feature packages; it inherits the browser-trust
 * fence and authentication) and the card POSTs to. Body: `ReportRequest` JSON;
 * response: `RpcResult<ReportView>` JSON.
 */
declare const REPORT_PATH = "/api/skills-anywhere/report";
/** The runtime-editable part of the plugin config. */
interface CatalogSettings {
  readonly catalog: {
    readonly limit: number;
    readonly pin: readonly string[];
    readonly hide: readonly string[];
  };
  readonly excludeSkills: readonly string[];
}
//#endregion
//#region src/provider.d.ts
interface ProviderLogger {
  readonly info: (message: string) => void;
  readonly warn: (message: string) => void;
  readonly debug?: (message: string) => void;
}
/** Skills-anywhere provider for the dsh skill registry. */
declare class SkillsAnywhereProvider implements SkillProvider {
  private config;
  private readonly log;
  private readonly control?;
  readonly name: string;
  private readonly watchers;
  private readonly polledFiles;
  private readonly watchedProjects;
  private syncTimer;
  private syncing;
  private syncQueued;
  /** Project roots the most recent sync run read sources for. */
  private lastSyncProjects;
  /** Aborts git processes of in-flight syncs on dispose (or when dsh aborts the provider). */
  private readonly abort;
  private readonly syncedProjects;
  private disposed;
  private invalidateTimer;
  private lastReport;
  private lastSync;
  /** Catalog state per project root (`''` for no cwd) from the latest `list()`. */
  private readonly catalogStates;
  constructor(config: ResolvedConfig, log: ProviderLogger, control?: SkillProviderControl | undefined);
  /** dsh calls this for every catalog refresh; `cwd` selects the project. */
  list(options?: SkillLookupOptions): Promise<SkillCandidate[] | SkillProviderObservation>;
  /** The configuration currently in force (runtime settings applied). */
  get currentConfig(): ResolvedConfig;
  /**
   * Replace the runtime-editable part of the configuration (catalog budget,
   * pins, hides, exclusions) and invalidate the catalog so the next `list()`
   * applies it. Everything else (roots, sync, watchers) stays as composed.
   */
  reconfigure(settings: CatalogSettings): void;
  /**
   * Everything the web card shows: the latest discovery report for the
   * project containing `cwd` (running one when none exists yet) with the
   * catalog state of every skill and the runtime settings in force.
   */
  snapshot(cwd?: string): Promise<ReportView>;
  /**
   * Catalog state of one published skill as of the latest `list()` for the
   * project containing `cwd`. `hidden` means the budget kept it out of the
   * model catalog; `disabled` means the skill's own frontmatter did.
   */
  catalogState(name: string, cwd?: string): Promise<CatalogState | undefined>;
  /** Re-read the winning file so edits are always reflected. */
  get(candidate: SkillCandidate, options?: SkillLookupOptions): Promise<SkillDefinition | undefined>;
  /** Report from the most recent `list()`; the CLI uses it for diagnostics. */
  report(): DiscoveryReport | undefined;
  /** Results of the most recent source sync. */
  syncResults(): readonly SyncResult[];
  /** Every configured source (config + files) for a cwd. */
  sources(cwd?: string): Promise<ResolvedSource[]>;
  /** Config- and user-level sources plus the project files of `projectRoots`. */
  private collectSources;
  /**
   * Clone or refresh every source. Concurrent calls share one run; a call that
   * names a project (or forces) while a run is in flight queues one follow-up
   * run, because the in-flight run read its source list before this request.
   */
  syncAll(cwd?: string, options?: {
    force?: boolean;
  }): Promise<SyncResult[]>;
  private runSync;
  /** Build the ordered root list for one cwd. */
  roots(cwd?: string): Promise<SkillRoot[]>;
  /** Stop timers and watchers. Safe to call more than once. */
  dispose(): Promise<void>;
  private readSources;
  private invalidate;
  /** Watch existing flat roots (bounded per project) and the sources files. */
  private watch;
  /** Bound the number of *projects* (not directories) whose roots are watched. */
  private admitProject;
  private pollFile;
}
//#endregion
export { ResolvedConfig as A, readLock as B, normalizeSkillName as C, Config as D, CatalogConfig as E, ResolvedSource as F, writeSourcesFile as G, resolveSource as H, SourceSpec as I, SyncResult as L, resolveConfig as M, LockEntry as N, DEFAULT_RANKS as O, LockFile as P, SyncStatus as R, isSkillName$1 as S, splitFrontmatter as T, sameRepository as U, readSourcesFile as V, syncSource as W, SkillRoot as _, ReportView as a, ParseResult as b, SkillView as c, DiscoveredSkill as d, DiscoveryReport as f, SkillOrigin as g, RootReport as h, REPORT_PATH as i, projectSourcesFile as j, RankConfig as k, CatalogState as l, InvalidSkill as m, SkillsAnywhereProvider as n, SETTINGS_NAMESPACE as o, DroppedSkill as p, CatalogSettings as r, SkillState as s, ProviderLogger as t, applyCatalogBudget as u, discover as v, parseSkillMarkdown as w, ParsedSkill as x, findProjectRoot as y, hasGit as z };