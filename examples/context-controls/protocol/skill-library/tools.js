import { n as searchSkills, t as queryTerms } from "./search-DUE-pmE0.js";
import z from "@deepseek-ai/schemastery";
import { isSkillName, renderSkillContent } from "@deepseek-ai/dsh-skill";
import { defineTool } from "@deepseek-ai/dsh-tools";
//#region src/tools.ts
const name = "skills-anywhere-tools";
const inject = ["skills", "tools"];
const Config = z.object({
	findLimit: z.number().default(10),
	findMaxLimit: z.number().default(50),
	find: z.boolean().default(true),
	open: z.boolean().default(true)
});
/** Whether a loaded definition may be handed to the model. */
function isOpenable(skill) {
	if (skill.invocation.modelInvocable) return true;
	const extra = skill.metadata?.skillsAnywhere;
	return extra?.catalog === "hidden" && extra.authorInvocation?.modelInvocable !== false;
}
function apply(ctx, config = {}) {
	const findLimit = Math.max(1, Math.floor(config.findLimit ?? 10));
	const findMaxLimit = Math.max(findLimit, Math.floor(config.findMaxLimit ?? 50));
	if (config.find ?? true) ctx.tools.register(defineTool({
		name: "find_skills",
		description: "Search every installed skill by keyword, including skills that are not listed in the session skill catalog. The catalog shows only a budgeted subset; when a task might match a skill you do not see listed, search here first, then load the match with open_skill (or with skill if it is listed).",
		parameters: {
			query: {
				type: "string",
				required: true,
				description: "Keywords describing the task or skill, e.g. \"pdf forms\", \"react testing\", \"docx\"."
			},
			limit: {
				type: "number",
				description: `Maximum matches to return (default ${findLimit}, max ${findMaxLimit}).`
			}
		},
		output: {
			schema: {
				type: "object",
				additionalProperties: false,
				properties: {
					total: {
						type: "number",
						required: true,
						description: "Skills searched."
					},
					unlisted: {
						type: "number",
						required: true,
						description: "Skills searched that are not in the session catalog."
					},
					matches: {
						type: "array",
						required: true,
						items: {
							type: "object",
							additionalProperties: false,
							properties: {
								name: {
									type: "string",
									required: true
								},
								description: {
									type: "string",
									required: true
								},
								listed: {
									type: "boolean",
									required: true,
									description: "True when the skill is in the session catalog and loadable with the skill tool."
								},
								source: {
									type: "string",
									required: true
								}
							}
						}
					}
				}
			},
			render: (_args, value) => {
				if (value.matches.length === 0) return [{
					type: "text",
					text: `No skills matched. ${value.total} skills searched (${value.unlisted} not in the catalog). Try different keywords.`
				}];
				const lines = value.matches.map((match) => `- ${match.name}${match.listed ? "" : " (not in catalog: load with open_skill)"} — ${match.description}`);
				return [{
					type: "text",
					text: [`${value.matches.length} of ${value.total} skills matched (${value.unlisted} searched skills are not in the catalog):`, ...lines].join("\n")
				}];
			}
		},
		async execute(args, exec) {
			const query = args.query.trim();
			if (query.length === 0) throw new Error("query must not be empty");
			const limit = Math.min(findMaxLimit, Math.max(1, Math.floor(args.limit ?? findLimit)));
			const lookup = {
				cwd: exec.agent?.session.header.cwd,
				signal: exec.signal,
				scope: exec.agent
			};
			const skills = await ctx.skills.list(lookup);
			const matches = [];
			for (const match of searchSkills(skills, query, skills.length)) {
				if (matches.length >= limit) break;
				if (!match.listed) {
					const definition = await ctx.skills.get(match.name, lookup);
					if (definition === void 0 || !isOpenable(definition)) continue;
				}
				matches.push(match);
			}
			return {
				total: skills.length,
				unlisted: skills.filter((skill) => !skill.invocation.modelInvocable).length,
				matches: matches.map((match) => ({
					name: match.name,
					description: match.description,
					listed: match.listed,
					source: match.source
				}))
			};
		},
		presentCall(args) {
			return {
				card: "generic",
				title: `Find skills: ${args.query}`,
				kind: "search",
				rawInput: args.query
			};
		}
	}));
	if (config.open ?? true) ctx.tools.register(defineTool({
		name: "open_skill",
		description: "Load the full instructions of a skill by exact name, including skills that find_skills reported as not listed in the session catalog. Use skill for catalog skills; use this for the rest.",
		parameters: { name: {
			type: "string",
			required: true,
			description: "Exact skill name as returned by find_skills."
		} },
		output: {
			schema: {
				type: "object",
				additionalProperties: false,
				properties: {
					name: {
						type: "string",
						required: true
					},
					provider: {
						type: "string",
						required: true
					},
					resourceBase: { oneOf: [
						{
							type: "object",
							additionalProperties: false,
							properties: {
								kind: {
									type: "string",
									required: true,
									const: "directory"
								},
								path: {
									type: "string",
									required: true
								}
							}
						},
						{
							type: "object",
							additionalProperties: false,
							properties: {
								kind: {
									type: "string",
									required: true,
									const: "url"
								},
								url: {
									type: "string",
									required: true
								}
							}
						},
						{
							type: "object",
							additionalProperties: false,
							properties: {
								kind: {
									type: "string",
									required: true,
									const: "opaque"
								},
								description: {
									type: "string",
									required: true
								}
							}
						}
					] },
					content: {
						type: "string",
						required: true
					}
				}
			},
			render: (_args, value) => [{
				type: "text",
				text: renderSkillContent(value)
			}]
		},
		async execute(args, exec) {
			if (!isSkillName(args.name)) throw new Error(`invalid skill name "${args.name}"`);
			const lookup = {
				cwd: exec.agent?.session.header.cwd,
				signal: exec.signal,
				scope: exec.agent
			};
			const skill = await ctx.skills.get(args.name, lookup);
			if (skill === void 0) throw new Error(`skill "${args.name}" is unknown or no longer available; search with find_skills`);
			if (!isOpenable(skill)) throw new Error(`skill "${args.name}" is not available for model invocation`);
			return {
				name: skill.name,
				provider: skill.provider,
				...skill.resourceBase !== void 0 ? { resourceBase: { ...skill.resourceBase } } : {},
				content: skill.content
			};
		},
		presentCall(args) {
			return {
				card: "generic",
				title: `Open skill ${args.name}`,
				kind: "read",
				rawInput: args.name
			};
		}
	}));
}
//#endregion
export { Config, apply, inject, isOpenable, name, queryTerms, searchSkills };
