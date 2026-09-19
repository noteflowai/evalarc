import { A as ResolvedConfig, B as readLock, C as normalizeSkillName, D as Config, E as CatalogConfig, F as ResolvedSource, G as writeSourcesFile, H as resolveSource, I as SourceSpec, L as SyncResult, M as resolveConfig, N as LockEntry, O as DEFAULT_RANKS, P as LockFile, R as SyncStatus, S as isSkillName, T as splitFrontmatter, U as sameRepository, V as readSourcesFile, W as syncSource, _ as SkillRoot, a as ReportView, b as ParseResult, c as SkillView, d as DiscoveredSkill, f as DiscoveryReport, g as SkillOrigin, h as RootReport, i as REPORT_PATH, j as projectSourcesFile, k as RankConfig, l as CatalogState, m as InvalidSkill, n as SkillsAnywhereProvider, o as SETTINGS_NAMESPACE, p as DroppedSkill, r as CatalogSettings, s as SkillState, t as ProviderLogger, u as applyCatalogBudget, v as discover, w as parseSkillMarkdown, x as ParsedSkill, y as findProjectRoot, z as hasGit } from "./provider-ulVIl-58.js";
import z from "@deepseek-ai/schemastery";
import { Context } from "@deepseek-ai/cordis";
//#region src/agents.d.ts
/**
 * Where other coding agents keep their Agent Skills.
 *
 * The table follows the conventions catalogued by the `skills` CLI
 * (https://github.com/vercel-labs/skills) and each agent's own docs. Two rows
 * are deliberately absent because the shipped `@deepseek-ai/dsh-skill-filesystem`
 * provider already scans them: `.agents/skills` (project and `~/.agents/skills`)
 * and `.dsh/skills`. Re-scanning them here would only produce duplicates.
 *
 * `project` is relative to the project root (nearest ancestor with `.git`, else
 * the cwd). `user` is relative to the home directory. Either may be absent.
 *
 * @module
 */
interface AgentSpec {
  /** Stable identifier, usable in `excludeAgents`. */
  readonly id: string;
  /** Human-readable product name. */
  readonly label: string;
  /** Project-level skills directory, relative to the project root. */
  readonly project?: string;
  /** User-level skills directory, relative to the home directory. */
  readonly user?: string;
}
export declare const AGENTS: readonly AgentSpec[];
/** Look up one agent by id. */
export declare function agentById(id: string): AgentSpec | undefined;
//#endregion
//#region src/origin.d.ts
/** One-line label such as `claude-code (user)`, `claude plugin discord @ official` or `git anthropics/skills`. */
export declare function originLabel(origin: SkillOrigin): string;
/** Group heading for the web card: where a skill physically lives. */
export declare function originGroup(origin: SkillOrigin): string;
//#endregion
//#region src/web.d.ts
/** Schema of the `skills-anywhere` settings namespace: the runtime-editable part of the plugin config. */
export declare const SettingsSchema: z<CatalogSettings>;
/** The composition entry for the settings namespace, derived from the resolved plugin config. */
export declare function settingsEntry(config: ResolvedConfig): CatalogSettings;
type RpcResult<T> = {
  readonly ok: true;
  readonly value: T;
} | {
  readonly ok: false;
  readonly error: {
    readonly code: string;
    readonly message: string;
    readonly details: object;
  };
};
interface WebLogger {
  info(message: string): void;
  warn(message: string): void;
}
/** Wire request of `skills-anywhere/report`. */
interface ReportRequest {
  /** Project directory whose project-level roots should be included. */
  readonly cwd?: string;
}
/** Serve one report request. Exported for tests and custom transports. */
export declare function handleReport(provider: SkillsAnywhereProvider | undefined, payload: unknown): Promise<RpcResult<ReportView>>;
/**
 * Attach the settings namespace and the report endpoint to `ctx`. `provider`
 * is a getter because dsh constructs the provider lazily through
 * `ctx.skills.registerProvider`.
 */
export declare function installWeb(ctx: Context, provider: () => SkillsAnywhereProvider | undefined, config: ResolvedConfig, log: WebLogger): void;
//#endregion
//#region src/index.d.ts
/** Cordis plugin name; stable across releases. */
export declare const name = "skills-anywhere";
/** The skill registry must exist before the provider can register. */
export declare const inject: string[];
/**
 * Register the skills-anywhere provider on `ctx.skills`, plus the runtime
 * settings namespace and the web report endpoint when their services exist.
 */
export declare function apply(ctx: Context, config?: Config): void;
//#endregion
export { type AgentSpec, type CatalogConfig, type CatalogSettings, type CatalogState, Config, type Config as ConfigInput, DEFAULT_RANKS, type DiscoveredSkill, type DiscoveryReport, type DroppedSkill, type InvalidSkill, type LockEntry, type LockFile, type ParseResult, type ParsedSkill, type ProviderLogger, REPORT_PATH, type RankConfig, type ReportRequest, type ReportView, type ResolvedConfig, type ResolvedSource, type RootReport, type RpcResult, SETTINGS_NAMESPACE, type SkillOrigin, type SkillRoot, type SkillState, type SkillView, SkillsAnywhereProvider, type SourceSpec, type SyncResult, type SyncStatus, applyCatalogBudget, discover, findProjectRoot, hasGit, isSkillName, normalizeSkillName, parseSkillMarkdown, projectSourcesFile, readLock, readSourcesFile, resolveConfig, resolveSource, sameRepository, splitFrontmatter, syncSource, writeSourcesFile };