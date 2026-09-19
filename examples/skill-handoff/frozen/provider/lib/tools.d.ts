import z from "@deepseek-ai/schemastery";
import { SkillDefinition } from "@deepseek-ai/dsh-skill";
import { Context } from "@deepseek-ai/cordis";
//#region src/search.d.ts
/**
 * Keyword search over skill summaries. Shared by the dsh tools and the MCP
 * server, so it imports nothing from dsh.
 *
 * @module
 */
/** The fields search needs; both dsh `SkillSummary` and discovered skills satisfy it. */
interface SearchableSkill {
  readonly name: string;
  readonly description: string;
  readonly whenToUse?: string;
  readonly source: string;
  readonly provider: string;
  readonly invocation: {
    readonly modelInvocable: boolean;
  };
}
interface SkillMatch {
  readonly name: string;
  readonly description: string;
  readonly source: string;
  readonly provider: string;
  /** Listed in the session catalog for the model. */
  readonly listed: boolean;
  readonly score: number;
}
/** Split a query into lowercase alphanumeric terms. */
export declare function queryTerms(query: string): string[];
/**
 * Rank skills against a keyword query. Name matches weigh most, then
 * description, `whenToUse`, and origin labels. Skills matching no term are
 * dropped; ties break alphabetically.
 */
export declare function searchSkills(skills: readonly SearchableSkill[], query: string, limit: number): SkillMatch[];
//#endregion
//#region src/tools.d.ts
export declare const name = "skills-anywhere-tools";
export declare const inject: string[];
export interface Config {
  /** Default number of matches `find_skills` returns. */
  readonly findLimit?: number;
  /** Maximum matches a single `find_skills` call may request. */
  readonly findMaxLimit?: number;
  /** Register `find_skills`. */
  readonly find?: boolean;
  /** Register `open_skill`. */
  readonly open?: boolean;
}
export declare const Config: z<Config>;
/** Whether a loaded definition may be handed to the model. */
export declare function isOpenable(skill: Pick<SkillDefinition, 'invocation' | 'metadata'>): boolean;
export declare function apply(ctx: Context, config?: Config): void;
//#endregion
export type { SearchableSkill, SkillMatch };