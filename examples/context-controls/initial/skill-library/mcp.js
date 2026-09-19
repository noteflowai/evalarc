import { b as resolveConfig, d as originLabel, g as readSkillBytes, t as SkillsAnywhereProvider } from "./provider-DIndg2HA.js";
import { a as parseSkillMarkdown, r as isSkillName } from "./skill-check-BYFdW99u.js";
import { n as searchSkills } from "./search-DUE-pmE0.js";
import { t as readBundle } from "./skill-bundle-2OVsba66.js";
import { createRequire } from "node:module";
import { createHash } from "node:crypto";
import { McpServer, ResourceTemplate } from "@modelcontextprotocol/server";
import { serveStdio } from "@modelcontextprotocol/server/stdio";
import { z } from "zod";
//#region src/mcp.ts
/**
* MCP server mode: the same skill pool the dsh provider publishes, exposed to
* any Model Context Protocol client (Claude Code, Cursor, Codex, Windsurf, …)
* as three tools and one resource template.
*
* - `list_skills`  — browse every model-invocable skill with its description
* - `find_skills`  — keyword search over names, descriptions and origins
* - `open_skill`   — load one skill's instructions plus its resource directory
* - `skill://{name}` resources for clients that prefer @-mentions
*
* The server imports nothing from dsh at runtime, so `npx dsh-skills-anywhere
* mcp` works on machines that never installed DeepSeek Harness.
*
* @module dsh-skills-anywhere/mcp
*/
const DEFAULT_CACHE_MS = 3e3;
const DEFAULT_FIND_LIMIT = 10;
const DEFAULT_MAX_LIMIT = 200;
const INSTRUCTIONS = [
	"This server exposes Agent Skills (SKILL.md folders) installed for other coding agents on this machine, inside Claude Code plugin marketplaces, and from configured git repositories.",
	"When a task might match a skill, call find_skills with a few keywords, then open_skill with the exact name to load its instructions.",
	"Skills may reference scripts and files relative to the directory returned by open_skill; read them from that directory only as needed."
].join(" ");
function isResolved(config) {
	return config !== void 0 && "stateDir" in config && typeof config.stateDir === "string";
}
function stderrLogger() {
	return {
		info: (message) => process.stderr.write(`${message}\n`),
		warn: (message) => process.stderr.write(`${message}\n`)
	};
}
function packageVersion() {
	try {
		const pkg = createRequire(import.meta.url)("../package.json");
		return typeof pkg.version === "string" ? pkg.version : "0.0.0";
	} catch {
		return "0.0.0";
	}
}
/** Skills the author allows a model to invoke, in catalog order. */
function modelSkills(report) {
	return report.skills.filter((skill) => skill.invocation.modelInvocable);
}
/** The same catalog search for direct clients and the MCP tool. */
function findModelSkills(report, query, limit = 10) {
	const trimmed = query.trim();
	if (trimmed.length === 0) throw new Error("query must not be empty");
	if (!Number.isSafeInteger(limit) || limit < 1) throw new Error("limit must be a positive safe integer");
	const skills = modelSkills(report);
	const matches = searchSkills(skills.map((skill) => ({
		...skill,
		source: originLabel(skill.origin),
		provider: "skills-anywhere"
	})), trimmed, limit);
	return {
		total: skills.length,
		matches: matches.map((match) => ({
			name: match.name,
			description: match.description,
			source: match.source
		}))
	};
}
/** Escape text for an XML attribute value. */
function escapeAttr(value) {
	return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
/** Escape text placed between tags. */
function escapeText(value) {
	return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
/**
* Render a skill the way dsh hands it to its model, so clients that already
* understand `<skill_content>` blocks see a familiar shape.
*/
function renderSkill(skill) {
	const declared = skill.declaredTools ?? [];
	return [
		`<skill_content name="${escapeAttr(skill.name)}">`,
		"<skill_resources>",
		`Base directory for this skill: ${escapeText(skill.directory)}`,
		"Resolve relative paths mentioned by this skill against the base directory before using them. Load referenced resources only as needed.",
		"</skill_resources>",
		...declared.length > 0 ? [
			"",
			"<skill_author_declared_tools>",
			`The author declared this skill needs only: ${escapeText(declared.join(", "))}.`,
			"This server cannot restrict your tools. Treat anything beyond that list as outside what the author asked for.",
			"</skill_author_declared_tools>"
		] : [],
		"",
		"<skill_instructions>",
		skill.content,
		"</skill_instructions>",
		"</skill_content>"
	].join("\n");
}
/** Re-read a discovered skill from disk so edits since discovery are honoured. */
async function openSkill(skill, lenient, includeBundle = false) {
	let raw;
	let bytes;
	const snapshot = includeBundle ? await readBundle(skill.directory) : void 0;
	try {
		bytes = snapshot?.skillBytes ?? await readSkillBytes(skill.path);
		raw = new TextDecoder("utf-8", {
			fatal: true,
			ignoreBOM: true
		}).decode(bytes);
	} catch {
		return;
	}
	const parsed = parseSkillMarkdown(raw, {
		fallbackName: skill.name,
		lenient
	});
	if (!parsed.ok) return void 0;
	if (!parsed.skill.invocation.modelInvocable) throw new Error(`skill "${skill.name}" is not available for model invocation (disabled by its author)`);
	return {
		sha256: createHash("sha256").update(bytes).digest("hex"),
		name: skill.name,
		description: parsed.skill.description,
		directory: skill.directory,
		path: skill.path,
		source: skill.source,
		content: parsed.skill.content,
		...Array.isArray(parsed.skill.metadata.allowedTools) && parsed.skill.metadata.allowedTools.length > 0 ? { declaredTools: parsed.skill.metadata.allowedTools } : {},
		...snapshot ? { bundle: snapshot.manifest } : {}
	};
}
/** Build a server over a standalone provider. Nothing is connected yet. */
function createSkillsAnywhereServer(options = {}) {
	const log = options.log ?? stderrLogger();
	const config = isResolved(options.config) ? options.config : resolveConfig({
		...options.config,
		watch: false
	});
	const cwd = options.cwd ?? process.cwd();
	const cacheMs = Math.max(0, options.cacheMs ?? DEFAULT_CACHE_MS);
	const findLimit = Math.max(1, Math.floor(options.findLimit ?? DEFAULT_FIND_LIMIT));
	const maxLimit = Math.max(findLimit, Math.floor(options.maxLimit ?? DEFAULT_MAX_LIMIT));
	const provider = new SkillsAnywhereProvider(config, log);
	const server = new McpServer({
		name: "dsh-skills-anywhere",
		version: packageVersion()
	}, { instructions: INSTRUCTIONS });
	let cached;
	let inflight;
	const empty = {
		skills: [],
		dropped: [],
		invalid: [],
		roots: [],
		complete: true
	};
	async function refresh(force = false) {
		if (!force && cached !== void 0 && Date.now() - cached.at < cacheMs) return cached.report;
		if (inflight !== void 0) return inflight;
		inflight = (async () => {
			try {
				await provider.list({ cwd });
				const report = provider.report() ?? empty;
				cached = {
					at: Date.now(),
					report
				};
				return report;
			} finally {
				inflight = void 0;
			}
		})();
		return inflight;
	}
	function clampLimit(limit, fallback) {
		return Math.min(maxLimit, Math.max(1, Math.floor(limit ?? fallback)));
	}
	server.registerTool("list_skills", {
		title: "List skills",
		description: "List installed Agent Skills (name, description, origin) available through this server. Use find_skills to search a large pool instead of paging through it.",
		inputSchema: {
			limit: z.number().int().min(1).max(maxLimit).optional().describe(`Maximum skills to return (default ${maxLimit}).`),
			offset: z.number().int().min(0).optional().describe("Skip this many skills (for paging).")
		},
		outputSchema: {
			total: z.number().describe("Model-invocable skills available."),
			skills: z.array(z.object({
				name: z.string(),
				description: z.string(),
				source: z.string()
			}))
		}
	}, async ({ limit, offset }) => {
		const skills = modelSkills(await refresh());
		const start = Math.max(0, Math.floor(offset ?? 0));
		const page = skills.slice(start, start + clampLimit(limit, maxLimit));
		const structured = {
			total: skills.length,
			skills: page.map((skill) => ({
				name: skill.name,
				description: skill.description,
				source: originLabel(skill.origin)
			}))
		};
		return {
			content: [{
				type: "text",
				text: skills.length === 0 ? "No skills found. Add a git source with `dsh-skills-anywhere add owner/repo` or install skills for any supported agent." : [`${page.length} of ${skills.length} skills:`, ...page.map((skill) => `- ${skill.name} — ${skill.description} [${originLabel(skill.origin)}]`)].join("\n")
			}],
			structuredContent: structured
		};
	});
	server.registerTool("find_skills", {
		title: "Find skills",
		description: "Search installed Agent Skills by keyword across names, descriptions and origins. Returns the best matches; load one with open_skill.",
		inputSchema: {
			query: z.string().min(1).describe("Keywords describing the task or skill, e.g. \"pdf forms\", \"react testing\", \"docx\"."),
			limit: z.number().int().min(1).max(maxLimit).optional().describe(`Maximum matches to return (default ${findLimit}).`)
		},
		outputSchema: {
			total: z.number().describe("Skills searched."),
			matches: z.array(z.object({
				name: z.string(),
				description: z.string(),
				source: z.string()
			}))
		}
	}, async ({ query, limit }) => {
		const trimmed = query.trim();
		const structured = findModelSkills(await refresh(), trimmed, clampLimit(limit, findLimit));
		const { matches, total } = structured;
		return {
			content: [{
				type: "text",
				text: matches.length === 0 ? `No skills matched "${trimmed}". ${total} skills searched; try different keywords or list_skills.` : [`${matches.length} of ${total} skills matched:`, ...matches.map((match) => `- ${match.name} — ${match.description} [${match.source}]`)].join("\n")
			}],
			structuredContent: structured
		};
	});
	async function lookup(name, includeBundle = false) {
		if (!isSkillName(name)) throw new Error(`invalid skill name "${name}"`);
		let report = await refresh();
		let skill = report.skills.find((entry) => entry.name === name);
		if (skill === void 0) {
			report = await refresh(true);
			skill = report.skills.find((entry) => entry.name === name);
		}
		if (skill === void 0) throw new Error(`skill "${name}" is unknown; search with find_skills`);
		if (!skill.invocation.modelInvocable) throw new Error(`skill "${name}" is not available for model invocation (disabled by its author)`);
		const opened = await openSkill(skill, config.lenient, includeBundle);
		if (opened === void 0) throw new Error(`skill "${name}" is no longer readable at ${skill.path}`);
		return opened;
	}
	server.registerTool("open_skill", {
		title: "Open skill",
		description: "Load the full instructions of an installed Agent Skill by exact name, together with the directory its scripts and references live in.",
		inputSchema: {
			name: z.string().min(1).describe("Exact skill name as returned by find_skills or list_skills."),
			expected_sha256: z.string().regex(/^[a-f0-9]{64}$/).optional().describe("Require these exact SKILL.md bytes, using a hash from check --json or an earlier open_skill. Excludes referenced files."),
			include_bundle: z.boolean().optional().describe("Also fingerprint all regular files below this skill directory; bounded reads, no execution."),
			expected_bundle_sha256: z.string().regex(/^[a-f0-9]{64}$/).optional().describe("Require the reviewed directory digest from bundle --json. Includes its scripts, references, assets and hidden files; excludes external dependencies. Implies include_bundle.")
		},
		outputSchema: {
			name: z.string(),
			description: z.string(),
			directory: z.string().describe("Absolute directory; resolve relative paths in the instructions against it."),
			path: z.string().describe("Absolute path of the SKILL.md file."),
			source: z.string(),
			content: z.string().describe("The skill instructions (Markdown body without frontmatter)."),
			sha256: z.string().describe("SHA-256 of original SKILL.md bytes, including frontmatter; not a security or resource verification."),
			declared_tools: z.array(z.string()).optional().describe("Tools the author declared this skill needs, from allowed-tools. Reported, not enforced: this server cannot restrict your tools. Absent when the author declared none, which is not a statement that the skill is unrestricted."),
			bundle: z.object({
				schema: z.literal("skills-anywhere-bundle-1"),
				sha256: z.string(),
				total_bytes: z.number(),
				files: z.array(z.object({
					path: z.string(),
					bytes: z.number(),
					sha256: z.string()
				}))
			}).optional().describe("Directory inventory at inspection time. Does not freeze files for later execution or authenticate an author.")
		}
	}, async ({ name, expected_sha256, include_bundle, expected_bundle_sha256 }) => {
		const skill = await lookup(name, include_bundle === true || expected_bundle_sha256 !== void 0);
		if (expected_sha256 !== void 0 && skill.sha256 !== expected_sha256) throw new Error("SKILL.md changed: expected_sha256 does not match; review the current file before loading instructions");
		if (expected_bundle_sha256 !== void 0 && skill.bundle?.sha256 !== expected_bundle_sha256) throw new Error("Skill bundle changed: expected_bundle_sha256 does not match; review scripts and resources before loading instructions");
		const { declaredTools, ...rest } = skill;
		return {
			content: [{
				type: "text",
				text: renderSkill(skill)
			}],
			structuredContent: {
				...rest,
				...declaredTools !== void 0 ? { declared_tools: [...declaredTools] } : {}
			}
		};
	});
	server.registerResource("skill", new ResourceTemplate("skill://{name}", {
		list: async () => ({ resources: modelSkills(await refresh()).map((skill) => ({
			uri: `skill://${skill.name}`,
			name: skill.name,
			description: skill.description,
			mimeType: "text/markdown"
		})) }),
		complete: { name: async (value) => modelSkills(await refresh()).map((skill) => skill.name).filter((name) => name.startsWith(value)) }
	}), {
		title: "Agent Skill",
		description: "Instructions of one installed Agent Skill, rendered with its resource directory.",
		mimeType: "text/markdown"
	}, async (uri, variables) => {
		const raw = variables.name;
		const skill = await lookup(Array.isArray(raw) ? raw[0] ?? "" : raw ?? "");
		return { contents: [{
			uri: uri.href,
			mimeType: "text/markdown",
			text: renderSkill(skill)
		}] };
	});
	return {
		server,
		provider,
		refresh,
		async close() {
			await server.close();
			await provider.dispose();
		}
	};
}
/** Serve over stdio until the client disconnects; resolves when closed. */
async function runStdio(options = {}) {
	const mcp = createSkillsAnywhereServer(options);
	let finish;
	const closed = new Promise((resolve) => {
		finish = resolve;
	});
	const handle = serveStdio(() => mcp.server, { onerror: (error) => (options.log ?? stderrLogger()).warn(error.message) });
	process.stdin.once("end", finish);
	process.once("SIGINT", finish);
	process.once("SIGTERM", finish);
	mcp.server.server.onclose = finish;
	try {
		if (process.stdin.readableEnded || process.stdin.destroyed) finish();
		await closed;
	} finally {
		process.stdin.off("end", finish);
		process.off("SIGINT", finish);
		process.off("SIGTERM", finish);
		await handle.close();
		await mcp.provider.dispose();
	}
}
//#endregion
export { createSkillsAnywhereServer, findModelSkills, modelSkills, openSkill, packageVersion, renderSkill, runStdio };
