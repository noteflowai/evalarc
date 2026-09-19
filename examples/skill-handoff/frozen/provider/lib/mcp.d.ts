import { A as ResolvedConfig, D as Config, d as DiscoveredSkill, f as DiscoveryReport, n as SkillsAnywhereProvider, t as ProviderLogger } from "./provider-ulVIl-58.js";
import { McpServer } from "@modelcontextprotocol/server";
//#region src/load-receipt.d.ts
/** A delivery record. The caller associates it with its own trace/span IDs. */
interface LoadReceipt {
  readonly schema: 'skills-anywhere-load-1';
  readonly load_id: string;
  readonly loaded_at: string;
  readonly provider: 'dsh-skills-anywhere';
  readonly provider_version: string;
  readonly name: string;
  readonly skill_sha256: string;
  readonly content_sha256: string;
  readonly bundle_sha256: string | null;
  readonly declared_tools: readonly string[] | null;
  readonly permissions_enforced: false;
}
//#endregion
//#region src/bundle-manifest.d.ts
declare const BUNDLE_SCHEMA: 'skills-anywhere-bundle-1';
interface BundleFile {
  readonly path: string;
  readonly bytes: number;
  readonly sha256: string;
}
interface BundleManifest {
  readonly schema: typeof BUNDLE_SCHEMA;
  readonly sha256: string;
  readonly total_bytes: number;
  readonly files: readonly BundleFile[];
}
//#endregion
//#region src/mcp.d.ts
export interface McpOptions {
  /** Project directory that selects project-level skill roots and sources. */
  readonly cwd?: string;
  /** Provider configuration; defaults follow the dsh plugin defaults. */
  readonly config?: Config | ResolvedConfig;
  /** Where diagnostics go. Defaults to stderr, which stdio MCP clients ignore. */
  readonly log?: ProviderLogger;
  /** How long one discovery pass is reused before rescanning (ms). */
  readonly cacheMs?: number;
  /** Default `find_skills` result count. */
  readonly findLimit?: number;
  /** Hard cap for `find_skills` and `list_skills` result counts. */
  readonly maxLimit?: number;
}
export interface SkillsAnywhereMcp {
  readonly server: McpServer;
  readonly provider: SkillsAnywhereProvider;
  /** Discover (or reuse the cached pass) and return the current pool. */
  refresh(force?: boolean): Promise<DiscoveryReport>;
  /** Close the transport and release watchers and timers. */
  close(): Promise<void>;
}
export interface OpenedSkill {
  readonly name: string;
  readonly description: string;
  readonly directory: string;
  readonly path: string;
  readonly source: string;
  readonly content: string;
  /** SHA-256 of the original SKILL.md bytes, including frontmatter. */
  readonly sha256: string;
  /**
   * Tools the author declared this skill needs, from `allowed-tools`.
   *
   * The origin agent may enforce this; MCP gives a server no way to restrict a
   * client's tools, so it is reported rather than applied. Dropping it silently
   * would hand the reader a skill that looks unrestricted when its author
   * narrowed it, which is the metadata loss that makes a skill riskier on the
   * second platform than on the first.
   */
  readonly declaredTools?: readonly string[];
  readonly bundle?: BundleManifest;
  /** Returned instruction identity; no execution or task-success assertion. */
  readonly receipt: LoadReceipt;
}
export declare function packageVersion(): string;
/** Skills the author allows a model to invoke, in catalog order. */
export declare function modelSkills(report: DiscoveryReport): DiscoveredSkill[];
/** The same catalog search for direct clients and the MCP tool. */
export declare function findModelSkills(report: DiscoveryReport, query: string, limit?: number): {
  total: number;
  matches: {
    name: string;
    description: string;
    source: string;
  }[];
};
/**
 * Render a skill the way dsh hands it to its model, so clients that already
 * understand `<skill_content>` blocks see a familiar shape.
 */
export declare function renderSkill(skill: Pick<OpenedSkill, 'name' | 'directory' | 'content' | 'declaredTools'>): string;
/** Re-read a discovered skill from disk so edits since discovery are honoured. */
export declare function openSkill(skill: DiscoveredSkill, lenient: boolean, includeBundle?: boolean): Promise<OpenedSkill | undefined>;
/** Build a server over a standalone provider. Nothing is connected yet. */
export declare function createSkillsAnywhereServer(options?: McpOptions): SkillsAnywhereMcp;
/** Serve over stdio until the client disconnects; resolves when closed. */
export declare function runStdio(options?: McpOptions): Promise<void>;
//#endregion