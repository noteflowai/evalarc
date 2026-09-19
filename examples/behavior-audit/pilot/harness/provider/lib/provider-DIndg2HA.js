import { a as parseSkillMarkdown, i as normalizeSkillName, t as MAX_SKILL_BYTES } from "./skill-check-BYFdW99u.js";
import { homedir } from "node:os";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import z from "@deepseek-ai/schemastery";
import { constants, unwatchFile, watchFile } from "node:fs";
import { mkdir, open, readFile, readdir, realpath, rename, rm, stat, writeFile } from "node:fs/promises";
import chokidar from "chokidar";
import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
//#region src/config.ts
/**
* Plugin configuration: the Schemastery schema Cordis validates, and the
* resolved shape the provider consumes.
*
* @module
*/
const DEFAULT_RANKS = {
	project: 250,
	user: 550,
	claudePlugins: 580,
	sources: 700
};
const DEFAULT_SYNC_INTERVAL_MS = 216e5;
const DEFAULT_SYNC_TIMEOUT_MS = 12e4;
const SourceSchema = z.union([z.string(), z.object({
	repo: z.string().required(),
	ref: z.string(),
	path: z.string(),
	rank: z.number()
})]);
const Config = z.object({
	providerName: z.string().default("skills-anywhere"),
	agents: z.boolean().default(true),
	excludeAgents: z.array(z.string()).default([]),
	extraProjectDirs: z.array(z.string()).default([]),
	extraUserDirs: z.array(z.string()).default([]),
	claudePlugins: z.boolean().default(true),
	sources: z.array(SourceSchema).default([]),
	sourcesFiles: z.boolean().default(true),
	cacheDir: z.string(),
	dshHome: z.string(),
	home: z.string(),
	sync: z.boolean().default(true),
	syncOnStart: z.boolean().default(true),
	syncIntervalMs: z.number().default(DEFAULT_SYNC_INTERVAL_MS),
	syncTimeoutMs: z.number().default(DEFAULT_SYNC_TIMEOUT_MS),
	maxDepth: z.number().default(5),
	dedupe: z.boolean().default(true),
	lenient: z.boolean().default(true),
	watch: z.boolean().default(true),
	excludeSkills: z.array(z.string()).default([]),
	ranks: z.object({
		project: z.number().default(DEFAULT_RANKS.project),
		user: z.number().default(DEFAULT_RANKS.user),
		claudePlugins: z.number().default(DEFAULT_RANKS.claudePlugins),
		sources: z.number().default(DEFAULT_RANKS.sources)
	}).default({ ...DEFAULT_RANKS }),
	catalog: z.object({
		limit: z.number().default(50),
		pin: z.array(z.string()).default([]),
		hide: z.array(z.string()).default([])
	}).default({
		limit: 50,
		pin: [],
		hide: []
	})
});
/** Expand a leading `~` against `home`. */
function expandHome(path, home) {
	if (path === "~") return home;
	if (path.startsWith("~/")) return join(home, path.slice(2));
	return path;
}
/** Apply defaults and resolve every path. */
function resolveConfig(config = {}, env = process.env) {
	const home = resolve(config.home ?? env.HOME ?? homedir());
	const dshHome = resolve(expandHome(config.dshHome ?? env.DSH_HOME ?? join(home, ".dsh"), home));
	const stateDir = join(dshHome, "skills-anywhere");
	const cacheDir = resolve(expandHome(config.cacheDir ?? join(stateDir, "cache"), home));
	const ranks = {
		...DEFAULT_RANKS,
		...stripUndefined(config.ranks ?? {})
	};
	return {
		providerName: config.providerName ?? "skills-anywhere",
		agents: config.agents ?? true,
		excludeAgents: new Set(config.excludeAgents ?? []),
		extraProjectDirs: (config.extraProjectDirs ?? []).map((dir) => dir.replace(/^\.?\/+/, "")),
		extraUserDirs: (config.extraUserDirs ?? []).map((dir) => resolve(expandHome(dir, home))),
		claudePlugins: config.claudePlugins ?? true,
		sources: config.sources ?? [],
		sourcesFiles: config.sourcesFiles ?? true,
		cacheDir,
		dshHome,
		home,
		sync: config.sync ?? true,
		syncOnStart: config.syncOnStart ?? true,
		syncIntervalMs: config.syncIntervalMs ?? 216e5,
		syncTimeoutMs: config.syncTimeoutMs ?? 12e4,
		maxDepth: config.maxDepth ?? 5,
		dedupe: config.dedupe ?? true,
		lenient: config.lenient ?? true,
		watch: config.watch ?? true,
		excludeSkills: config.excludeSkills ?? [],
		ranks,
		catalog: {
			limit: Math.max(0, Math.floor(config.catalog?.limit ?? 50)),
			pin: new Set(config.catalog?.pin ?? []),
			hide: new Set(config.catalog?.hide ?? [])
		},
		stateDir,
		userSourcesFile: join(stateDir, "sources.json"),
		lockFile: join(stateDir, "lock.json")
	};
}
/** Project-level sources file for a project root. */
function projectSourcesFile(projectRoot) {
	return join(projectRoot, ".dsh", "skills-anywhere.json");
}
function stripUndefined(value) {
	return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== void 0));
}
//#endregion
//#region src/skill-input.ts
/** Bounded reads shared by file checks and MCP instruction loading. */
async function readSkillBytes(path) {
	const handle = await open(path, constants.O_RDONLY | (constants.O_NONBLOCK ?? 0));
	try {
		const stat = await handle.stat();
		if (!stat.isFile()) throw new Error("Choose a regular Markdown file.");
		if (stat.size > 131072) throw new Error("Choose a SKILL.md of 128 KiB or less.");
		const buffer = Buffer.alloc(MAX_SKILL_BYTES + 1);
		let size = 0;
		while (size < buffer.length) {
			const { bytesRead } = await handle.read(buffer, size, buffer.length - size, null);
			if (bytesRead === 0) break;
			size += bytesRead;
		}
		if (size > 131072) throw new Error("Choose a SKILL.md of 128 KiB or less.");
		return buffer.subarray(0, size);
	} finally {
		await handle.close();
	}
}
//#endregion
//#region src/agents.ts
const AGENTS = [
	{
		id: "claude-code",
		label: "Claude Code",
		project: ".claude/skills",
		user: ".claude/skills"
	},
	{
		id: "codex",
		label: "OpenAI Codex",
		user: ".codex/skills"
	},
	{
		id: "cursor",
		label: "Cursor",
		user: ".cursor/skills"
	},
	{
		id: "gemini-cli",
		label: "Gemini CLI",
		user: ".gemini/skills"
	},
	{
		id: "github-copilot",
		label: "GitHub Copilot",
		user: ".copilot/skills"
	},
	{
		id: "antigravity",
		label: "Antigravity",
		user: ".gemini/antigravity/skills"
	},
	{
		id: "antigravity-cli",
		label: "Antigravity CLI",
		user: ".gemini/antigravity-cli/skills"
	},
	{
		id: "opencode",
		label: "OpenCode",
		user: ".config/opencode/skills"
	},
	{
		id: "universal",
		label: "Amp / Replit / Universal",
		user: ".config/agents/skills"
	},
	{
		id: "windsurf",
		label: "Windsurf",
		project: ".windsurf/skills",
		user: ".codeium/windsurf/skills"
	},
	{
		id: "kiro-cli",
		label: "Kiro CLI",
		project: ".kiro/skills",
		user: ".kiro/skills"
	},
	{
		id: "goose",
		label: "Goose",
		project: ".goose/skills",
		user: ".config/goose/skills"
	},
	{
		id: "grok",
		label: "Grok Build",
		project: ".grok/skills",
		user: ".grok/skills"
	},
	{
		id: "hermes-agent",
		label: "Hermes Agent",
		project: ".hermes/skills",
		user: ".hermes/skills"
	},
	{
		id: "roo",
		label: "Roo Code",
		project: ".roo/skills",
		user: ".roo/skills"
	},
	{
		id: "cline",
		label: "Cline",
		user: ".cline/skills"
	},
	{
		id: "continue",
		label: "Continue",
		project: ".continue/skills",
		user: ".continue/skills"
	},
	{
		id: "junie",
		label: "Junie",
		project: ".junie/skills",
		user: ".junie/skills"
	},
	{
		id: "qwen-code",
		label: "Qwen Code",
		project: ".qwen/skills",
		user: ".qwen/skills"
	},
	{
		id: "trae",
		label: "Trae",
		project: ".trae/skills",
		user: ".trae/skills"
	},
	{
		id: "trae-cn",
		label: "Trae CN",
		user: ".trae-cn/skills"
	},
	{
		id: "augment",
		label: "Augment",
		project: ".augment/skills",
		user: ".augment/skills"
	},
	{
		id: "droid",
		label: "Droid (Factory)",
		user: ".factory/skills"
	},
	{
		id: "kilo",
		label: "Kilo Code",
		user: ".kilo/skills"
	},
	{
		id: "deepagents",
		label: "Deep Agents",
		user: ".deepagents/agent/skills"
	},
	{
		id: "devin",
		label: "Devin for Terminal",
		project: ".devin/skills",
		user: ".config/devin/skills"
	},
	{
		id: "crush",
		label: "Crush",
		project: ".crush/skills",
		user: ".config/crush/skills"
	},
	{
		id: "firebender",
		label: "Firebender",
		user: ".firebender/skills"
	},
	{
		id: "forgecode",
		label: "ForgeCode",
		project: ".forge/skills",
		user: ".forge/skills"
	},
	{
		id: "fx",
		label: "fx",
		project: ".fx/skills",
		user: ".fx/skills"
	},
	{
		id: "iflow-cli",
		label: "iFlow CLI",
		project: ".iflow/skills",
		user: ".iflow/skills"
	},
	{
		id: "inference-sh",
		label: "inference.sh",
		project: ".inferencesh/skills",
		user: ".inferencesh/skills"
	},
	{
		id: "jazz",
		label: "Jazz",
		project: ".jazz/skills",
		user: ".jazz/skills"
	},
	{
		id: "kimchi",
		label: "Kimchi",
		project: ".kimchi/skills",
		user: ".config/kimchi/harness/skills"
	},
	{
		id: "kode",
		label: "Kode",
		project: ".kode/skills",
		user: ".kode/skills"
	},
	{
		id: "lingma",
		label: "Lingma",
		project: ".lingma/skills",
		user: ".lingma/skills"
	},
	{
		id: "mcpjam",
		label: "MCPJam",
		project: ".mcpjam/skills",
		user: ".mcpjam/skills"
	},
	{
		id: "minimax-code",
		label: "MiniMax Code",
		project: ".minimax/skills",
		user: ".minimax/skills"
	},
	{
		id: "mistral-vibe",
		label: "Mistral Vibe",
		project: ".vibe/skills",
		user: ".vibe/skills"
	},
	{
		id: "moxby",
		label: "Moxby",
		project: ".moxby/skills",
		user: ".moxby/skills"
	},
	{
		id: "mux",
		label: "Mux",
		project: ".mux/skills",
		user: ".mux/skills"
	},
	{
		id: "neovate",
		label: "Neovate",
		project: ".neovate/skills",
		user: ".neovate/skills"
	},
	{
		id: "ona",
		label: "Ona",
		project: ".ona/skills",
		user: ".ona/skills"
	},
	{
		id: "openclaw",
		label: "OpenClaw",
		user: ".openclaw/skills"
	},
	{
		id: "openhands",
		label: "OpenHands",
		project: ".openhands/skills",
		user: ".openhands/skills"
	},
	{
		id: "pi",
		label: "Pi",
		project: ".pi/skills",
		user: ".pi/agent/skills"
	},
	{
		id: "pochi",
		label: "Pochi",
		project: ".pochi/skills",
		user: ".pochi/skills"
	},
	{
		id: "posit-assistant",
		label: "Posit Assistant",
		project: ".posit/assistant/skills",
		user: ".posit/assistant/skills"
	},
	{
		id: "qoder",
		label: "Qoder",
		project: ".qoder/skills",
		user: ".qoder/skills"
	},
	{
		id: "qoder-cn",
		label: "Qoder CN",
		user: ".qoder-cn/skills"
	},
	{
		id: "reasonix",
		label: "Reasonix",
		project: ".reasonix/skills",
		user: ".reasonix/skills"
	},
	{
		id: "rovodev",
		label: "Rovo Dev",
		project: ".rovodev/skills",
		user: ".rovodev/skills"
	},
	{
		id: "tabnine-cli",
		label: "Tabnine CLI",
		project: ".tabnine/agent/skills",
		user: ".tabnine/agent/skills"
	},
	{
		id: "terramind",
		label: "Terramind",
		project: ".terramind/skills",
		user: ".terramind/skills"
	},
	{
		id: "tinycloud",
		label: "Tinycloud",
		project: ".tinycloud/skills",
		user: ".tinycloud/skills"
	},
	{
		id: "zcode",
		label: "ZCode",
		project: ".zcode/skills",
		user: ".zcode/skills"
	},
	{
		id: "zencoder",
		label: "Zencoder / Zenflow",
		project: ".zencoder/skills",
		user: ".zencoder/skills"
	},
	{
		id: "adal",
		label: "AdaL",
		project: ".adal/skills",
		user: ".adal/skills"
	},
	{
		id: "aider-desk",
		label: "AiderDesk",
		project: ".aider-desk/skills",
		user: ".aider-desk/skills"
	},
	{
		id: "astrbot",
		label: "AstrBot",
		user: ".astrbot/data/skills"
	},
	{
		id: "autohand-code",
		label: "Autohand Code CLI",
		project: ".autohand/skills",
		user: ".autohand/skills"
	},
	{
		id: "bob",
		label: "IBM Bob",
		project: ".bob/skills",
		user: ".bob/skills"
	},
	{
		id: "codearts-agent",
		label: "CodeArts Agent",
		project: ".codeartsdoer/skills",
		user: ".codeartsdoer/skills"
	},
	{
		id: "codebuddy",
		label: "CodeBuddy",
		project: ".codebuddy/skills",
		user: ".codebuddy/skills"
	},
	{
		id: "codemaker",
		label: "Codemaker",
		project: ".codemaker/skills",
		user: ".codemaker/skills"
	},
	{
		id: "codestudio",
		label: "Code Studio",
		project: ".codestudio/skills",
		user: ".codestudio/skills"
	},
	{
		id: "command-code",
		label: "Command Code",
		project: ".commandcode/skills",
		user: ".commandcode/skills"
	},
	{
		id: "cortex",
		label: "Cortex Code",
		project: ".cortex/skills",
		user: ".snowflake/cortex/skills"
	}
];
const AGENT_INDEX = new Map(AGENTS.map((agent) => [agent.id, agent]));
/** Look up one agent by id. */
function agentById(id) {
	return AGENT_INDEX.get(id);
}
//#endregion
//#region src/discover.ts
/**
* Filesystem discovery: turn a list of roots into deduplicated skill entries.
*
* Two walk modes exist. `flat` mirrors the dsh convention (direct
* `<name>/SKILL.md` bundles plus flat `<name>.md` files). `nested` walks a tree
* to a bounded depth and treats every directory holding a `SKILL.md` as a
* skill, which is what git repositories full of skills and Claude Code plugin
* marketplaces need.
*
* @module
*/
const DEFAULT_NESTED_DEPTH = 5;
const ROOT_CONCURRENCY = 8;
const FILE_CONCURRENCY = 16;
/** Map with at most `limit` calls in flight; results keep input order. */
async function mapLimit(items, limit, fn) {
	const results = Array.from({ length: items.length });
	let next = 0;
	const worker = async () => {
		while (next < items.length) {
			const index = next++;
			results[index] = await fn(items[index]);
		}
	};
	await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
	return results;
}
const SKIP_DIRS = /* @__PURE__ */ new Set([
	".git",
	"node_modules",
	".hg",
	".svn",
	"__pycache__",
	".venv",
	"venv",
	"dist",
	"build"
]);
const FLAT_IGNORED_FILES = /* @__PURE__ */ new Set([
	"README.md",
	"README.zh.md",
	"AGENTS.md",
	"CLAUDE.md",
	"GEMINI.md",
	"LICENSE.md",
	"CHANGELOG.md",
	"CONTRIBUTING.md"
]);
/** Discover skills under every root, then deduplicate across roots. */
async function discover(roots, options = {}) {
	const dedupe = options.dedupe ?? true;
	const lenient = options.lenient ?? true;
	const excluded = new Set(options.excludeSkills ?? []);
	const found = [];
	const invalid = [];
	const rootReports = [];
	let complete = true;
	const scans = await mapLimit(roots, ROOT_CONCURRENCY, async (root) => {
		options.signal?.throwIfAborted();
		let exists = true;
		let count = 0;
		const skills = [];
		const rejected = [];
		let ok = true;
		try {
			if (!(await stat(root.path)).isDirectory()) exists = false;
		} catch (error) {
			if (!isAbsent$1(error)) {
				ok = false;
				options.warn?.(`skills-anywhere: cannot access ${root.path}: ${String(error)}`);
			}
			exists = false;
		}
		if (exists) try {
			const files = root.mode === "flat" ? await listFlat(root.path) : await listNested(root.path, root.maxDepth ?? DEFAULT_NESTED_DEPTH, options.signal);
			const entries = await mapLimit(files, FILE_CONCURRENCY, async (file) => {
				options.signal?.throwIfAborted();
				return readSkill(file, root, lenient);
			});
			for (const [index, entry] of entries.entries()) if (entry.ok) {
				skills.push(entry.skill);
				count += 1;
			} else rejected.push({
				path: files[index].path,
				root,
				reason: entry.reason
			});
		} catch (error) {
			if (options.signal?.aborted) throw error;
			ok = false;
			options.warn?.(`skills-anywhere: discovery under ${root.path} failed: ${String(error)}`);
		}
		return {
			report: {
				root,
				exists,
				count
			},
			skills,
			invalid: rejected,
			ok
		};
	});
	for (const scan of scans) {
		found.push(...scan.skills);
		invalid.push(...scan.invalid);
		rootReports.push(scan.report);
		if (!scan.ok) complete = false;
	}
	const rootOrder = new Map(roots.map((root, index) => [root, index]));
	found.sort((left, right) => left.rank - right.rank || (rootOrder.get(left.root) ?? 0) - (rootOrder.get(right.root) ?? 0) || left.path.localeCompare(right.path));
	const dropped = [];
	const skills = [];
	const keptByHash = /* @__PURE__ */ new Map();
	const seenContent = /* @__PURE__ */ new Map();
	const realPaths = /* @__PURE__ */ new Map();
	const real = (path) => {
		let resolved = realPaths.get(path);
		if (resolved === void 0) {
			resolved = realKey(path);
			realPaths.set(path, resolved);
		}
		return resolved;
	};
	for (const skill of found) {
		if (excluded.has(skill.name)) {
			dropped.push({
				skill,
				winner: skill,
				reason: "excluded"
			});
			continue;
		}
		if (dedupe) {
			const sameHash = keptByHash.get(skill.contentHash);
			if (sameHash !== void 0) {
				const fileKey = await real(skill.path);
				let fileWinner;
				for (const other of sameHash) if (await real(other.path) === fileKey) {
					fileWinner = other;
					break;
				}
				if (fileWinner !== void 0) {
					dropped.push({
						skill,
						winner: fileWinner,
						reason: "same-file"
					});
					continue;
				}
				const contentWinner = seenContent.get(`${skill.name}\0${skill.contentHash}`);
				if (contentWinner !== void 0) {
					dropped.push({
						skill,
						winner: contentWinner,
						reason: "same-content"
					});
					continue;
				}
				sameHash.push(skill);
			} else keptByHash.set(skill.contentHash, [skill]);
			seenContent.set(`${skill.name}\0${skill.contentHash}`, skill);
		}
		skills.push(skill);
	}
	const published = [];
	for (const skill of disambiguate(skills)) if (excluded.has(skill.name)) dropped.push({
		skill,
		winner: skill,
		reason: "excluded"
	});
	else published.push(skill);
	return {
		skills: published,
		dropped,
		invalid,
		roots: rootReports,
		complete
	};
}
/**
* Different skills that share a name (three Claude Code plugins each shipping
* `configure`, say) would collapse to one entry in the dsh registry. When a
* skill you authored (an agent directory) is involved, it keeps the bare name
* and the others are prefixed with their plugin, repository, or agent. When
* every member of the group comes from a plugin marketplace or a git source,
* all of them are prefixed, because a bare `configure` would be meaningless.
*/
function disambiguate(skills) {
	const groups = /* @__PURE__ */ new Map();
	for (const skill of skills) {
		const group = groups.get(skill.name);
		if (group === void 0) groups.set(skill.name, [skill]);
		else group.push(skill);
	}
	const taken = new Set(skills.map((skill) => skill.name));
	const renamed = /* @__PURE__ */ new Map();
	for (const [name, group] of groups) {
		if (group.length < 2) continue;
		const allThirdParty = group.every((skill) => skill.origin.kind === "claude-plugins" || skill.origin.kind === "source");
		const toRename = allThirdParty ? group : group.slice(1);
		if (allThirdParty) taken.delete(name);
		for (const skill of toRename) {
			const stem = `${collisionPrefix(skill)}-${name}`;
			let candidate = normalizeSkillName(stem) ?? name;
			let counter = 2;
			while (taken.has(candidate)) {
				const suffix = `-${counter}`;
				const base = stem.slice(0, Math.max(1, 64 - suffix.length));
				candidate = normalizeSkillName(`${base}${suffix}`) ?? `${name.slice(0, 64 - suffix.length)}${suffix}`;
				counter += 1;
			}
			taken.add(candidate);
			renamed.set(skill, candidate);
		}
	}
	return skills.map((skill) => {
		const candidate = renamed.get(skill);
		if (candidate === void 0) return skill;
		const warning = `name "${skill.name}" collides with another skill; published as "${candidate}"`;
		const extra = skill.metadata.skillsAnywhere;
		return {
			...skill,
			name: candidate,
			warnings: [...skill.warnings, warning],
			metadata: {
				...skill.metadata,
				skillsAnywhere: {
					...extra,
					renamedFrom: skill.name,
					warnings: [...extra?.warnings ?? [], warning]
				}
			}
		};
	});
}
function collisionPrefix(skill) {
	const { origin } = skill;
	if (origin.plugin !== void 0) return origin.plugin;
	if (origin.repo !== void 0) {
		const segments = origin.repo.split("/").filter((segment) => segment.length > 0);
		return segments[segments.length - 1] ?? "source";
	}
	if (origin.agent !== void 0) return origin.agent;
	return basename(skill.root.path);
}
async function listFlat(root) {
	return (await mapLimit((await readdir(root, { withFileTypes: true })).toSorted((left, right) => left.name.localeCompare(right.name)), FILE_CONCURRENCY, async (entry) => {
		const path = join(root, entry.name);
		if (entry.name.startsWith(".")) return void 0;
		if (entry.isDirectory() || entry.isSymbolicLink()) {
			const skillFile = join(path, "SKILL.md");
			return await isFile(skillFile) ? {
				path: skillFile,
				directory: path,
				fallbackName: entry.name
			} : void 0;
		}
		if (entry.isFile() && entry.name.endsWith(".md") && !FLAT_IGNORED_FILES.has(entry.name)) return {
			path,
			directory: root,
			fallbackName: entry.name.slice(0, -3)
		};
	})).filter((file) => file !== void 0);
}
async function listNested(root, maxDepth, signal) {
	const visited = /* @__PURE__ */ new Set();
	const walk = async (dir, depth) => {
		signal?.throwIfAborted();
		const files = [];
		const skillFile = join(dir, "SKILL.md");
		if (await isFile(skillFile)) {
			files.push({
				path: skillFile,
				directory: dir,
				fallbackName: basename(dir)
			});
			if (depth > 0) return files;
		}
		if (depth >= maxDepth) return files;
		let entries;
		try {
			entries = await readdir(dir, { withFileTypes: true });
		} catch {
			return files;
		}
		const sorted = entries.toSorted((left, right) => left.name.localeCompare(right.name));
		const resolved = await mapLimit(sorted, FILE_CONCURRENCY, async (entry) => {
			if (SKIP_DIRS.has(entry.name)) return void 0;
			if (!(entry.isDirectory() || entry.isSymbolicLink())) return void 0;
			const child = join(dir, entry.name);
			if (entry.isSymbolicLink() && !await isDirectory(child)) return void 0;
			try {
				return await realpath(child);
			} catch {
				return;
			}
		});
		const admitted = [];
		for (const [index, real] of resolved.entries()) {
			if (real === void 0 || visited.has(real)) continue;
			visited.add(real);
			admitted.push(join(dir, sorted[index].name));
		}
		const nested = await mapLimit(admitted, FILE_CONCURRENCY, (child) => walk(child, depth + 1));
		for (const list of nested) files.push(...list);
		return files;
	};
	try {
		visited.add(await realpath(root));
	} catch {
		return [];
	}
	return walk(root, 0);
}
async function readSkill(file, root, lenient) {
	let raw;
	try {
		raw = await readFile(file.path, "utf8");
	} catch (error) {
		return {
			ok: false,
			reason: `unreadable: ${String(error)}`
		};
	}
	if (raw.includes("�")) return {
		ok: false,
		reason: "not UTF-8 text"
	};
	const parsed = parseSkillMarkdown(raw, {
		fallbackName: file.fallbackName,
		lenient
	});
	if (!parsed.ok) return parsed;
	const origin = enrichOrigin(root, file.directory);
	const metadata = {
		...parsed.skill.metadata,
		skillsAnywhere: {
			origin,
			root: root.path,
			relativePath: relative(root.path, file.path).split(sep).join("/"),
			...parsed.skill.warnings.length > 0 ? { warnings: parsed.skill.warnings } : {}
		}
	};
	return {
		ok: true,
		skill: {
			name: parsed.skill.name,
			description: parsed.skill.description,
			...parsed.skill.whenToUse !== void 0 ? { whenToUse: parsed.skill.whenToUse } : {},
			invocation: parsed.skill.invocation,
			source: root.source,
			rank: root.rank,
			path: file.path,
			directory: file.directory,
			metadata,
			origin,
			root,
			contentHash: createHash("sha1").update(parsed.skill.content).digest("hex"),
			warnings: parsed.skill.warnings
		}
	};
}
/** Fill marketplace/plugin names for Claude Code plugin roots from the path shape. */
function enrichOrigin(root, directory) {
	if (root.origin.kind !== "claude-plugins") return root.origin;
	const segments = relative(root.path, directory).split(sep);
	const skillsIndex = segments.lastIndexOf("skills");
	const marketplace = segments[0];
	const plugin = skillsIndex > 0 ? segments[skillsIndex - 1] : void 0;
	return {
		...root.origin,
		...marketplace !== void 0 ? { marketplace } : {},
		...plugin !== void 0 && !/^\d+\.\d+/.test(plugin) ? { plugin } : skillsIndex > 1 ? { plugin: segments[skillsIndex - 2] } : {}
	};
}
async function realKey(path) {
	try {
		return await realpath(path);
	} catch {
		return path;
	}
}
async function isFile(path) {
	try {
		return (await stat(path)).isFile();
	} catch {
		return false;
	}
}
async function isDirectory(path) {
	try {
		return (await stat(path)).isDirectory();
	} catch {
		return false;
	}
}
function isAbsent$1(error) {
	return typeof error === "object" && error !== null && "code" in error && (error.code === "ENOENT" || error.code === "ENOTDIR");
}
/** Nearest ancestor of `cwd` containing `.git`, else `cwd` itself (the dsh rule). */
async function findProjectRoot(cwd) {
	let current = cwd;
	while (true) {
		try {
			await stat(join(current, ".git"));
			return current;
		} catch {}
		const parent = dirname(current);
		if (parent === current) return cwd;
		current = parent;
	}
}
//#endregion
//#region src/origin.ts
/** One-line label such as `claude-code (user)`, `claude plugin discord @ official` or `git anthropics/skills`. */
function originLabel(origin) {
	switch (origin.kind) {
		case "agent": return `${origin.agent ?? "agent"} (${origin.scope ?? "?"})`;
		case "claude-plugins": return `claude plugin ${origin.plugin ?? "?"}${origin.marketplace !== void 0 ? ` @ ${origin.marketplace}` : ""}`;
		case "source": return `git ${origin.repo ?? "?"}`;
		default: return `custom (${origin.scope ?? "?"})`;
	}
}
/** Group heading for the web card: where a skill physically lives. */
function originGroup(origin) {
	switch (origin.kind) {
		case "agent": return origin.scope === "project" ? "Project skill directories" : "User skill directories";
		case "claude-plugins": return "Claude Code plugins";
		case "source": return "Git sources";
		default: return origin.scope === "project" ? "Project skill directories" : "User skill directories";
	}
}
//#endregion
//#region src/catalog.ts
/** Author-disabled skills never count; pins precede the remaining eligible skills. */
function applyCatalogBudget(skills, catalog) {
	const states = /* @__PURE__ */ new Map();
	const eligible = [];
	for (const skill of skills) if (!skill.invocation.modelInvocable) states.set(skill.name, "disabled");
	else if (catalog.hide.has(skill.name)) states.set(skill.name, "hidden");
	else eligible.push(skill);
	[...eligible.filter((skill) => catalog.pin.has(skill.name)), ...eligible.filter((skill) => !catalog.pin.has(skill.name))].forEach((skill, index) => {
		states.set(skill.name, catalog.limit === 0 || index < catalog.limit ? "visible" : "hidden");
	});
	return states;
}
//#endregion
//#region src/sources.ts
/**
* Git skill sources: parse `owner/repo`-style specs, keep a shallow clone per
* repository in a local cache, and record what was synced in a lock file.
*
* Network work happens only here. Discovery reads the cached checkout, so a
* failed sync degrades to "yesterday's skills" instead of an empty catalog.
*
* @module
*/
const execFileAsync = promisify(execFile);
const SHA_LIKE = /^[0-9a-f]{7,40}$/i;
const GITHUB_TREE = /^https?:\/\/github\.com\/([^/]+)\/([^/#?]+?)(?:\.git)?\/tree\/([^/#?]+)(?:\/(.*?))?\/?$/;
const GITHUB_PLAIN = /^https?:\/\/github\.com\/([^/]+)\/([^/#?]+?)(?:\.git)?\/?$/;
const GIT_URL = /^(?:https?|ssh|git):\/\/|^git@|^[\w.-]+@[\w.-]+:/;
/** Normalise a string or object spec into a resolved source. */
function resolveSource(input, cacheDir) {
	const spec = typeof input === "string" ? parseSourceString(input) : input;
	let repo = spec.repo.trim();
	let ref = spec.ref;
	let subpath = spec.path;
	const suffix = /^(.*?)[@#]([^@#/]+)$/.exec(repo);
	if (suffix !== null && !GIT_URL.test(repo) && !repo.startsWith("file:") && !isAbsolute(repo)) {
		repo = suffix[1];
		ref ??= suffix[2];
	}
	let url;
	let id;
	let display;
	const tree = GITHUB_TREE.exec(repo);
	const plain = GITHUB_PLAIN.exec(repo);
	if (tree !== null) {
		const [, owner, name, treeRef, treePath] = tree;
		url = `https://github.com/${owner}/${name}.git`;
		id = `github.com/${owner}/${name}`;
		display = `${owner}/${name}`;
		ref ??= treeRef;
		if (treePath !== void 0 && treePath.length > 0) subpath ??= treePath;
	} else if (plain !== null) {
		const [, owner, name] = plain;
		url = `https://github.com/${owner}/${name}.git`;
		id = `github.com/${owner}/${name}`;
		display = `${owner}/${name}`;
	} else if (repo.startsWith("file:")) {
		const local = resolve(fileURLToPath(repo));
		url = local;
		id = `local/${shortHash(local)}`;
		display = local;
	} else if (isAbsolute(repo) || repo.startsWith("./") || repo.startsWith("../")) {
		const local = resolve(repo);
		url = local;
		id = `local/${shortHash(local)}`;
		display = local;
	} else if (GIT_URL.test(repo)) {
		url = repo;
		const cleaned = repo.replace(/^[a-z+]+:\/\//i, "").replace(/^git@/, "").replace(/:/, "/").replace(/\.git$/, "");
		id = cleaned.toLowerCase();
		display = cleaned;
	} else {
		const parts = trimSlashes(repo.replace(/^(?:github|gh):/, "")).split("/");
		if (parts.length < 2 || parts[0]?.length === 0 || parts[1]?.length === 0) throw new Error(`skills-anywhere: cannot parse source "${spec.repo}" (expected owner/repo, a git URL, or a local path)`);
		const owner = parts[0];
		const name = parts[1].replace(/\.git$/, "");
		url = `https://github.com/${owner}/${name}.git`;
		id = `github.com/${owner}/${name}`;
		display = `${owner}/${name}`;
		if (parts.length > 2) subpath ??= parts.slice(2).join("/");
	}
	const segments = id.split("/");
	if (segments.some((segment) => !isPlainSegment(segment))) throw new Error(`skills-anywhere: cannot parse source "${spec.repo}" (invalid path segment in ${id})`);
	if (ref !== void 0) segments[segments.length - 1] = `${segments[segments.length - 1]}@${ref.replace(/[^\w.-]+/g, "_")}`;
	const dir = join(cacheDir, ...segments);
	if (!isInside(cacheDir, dir)) throw new Error(`skills-anywhere: source "${spec.repo}" resolves outside the cache directory`);
	const scanDir = subpath !== void 0 && subpath.length > 0 ? join(dir, ...subpath.split("/")) : dir;
	if (scanDir !== dir && !isInside(dir, scanDir)) throw new Error(`skills-anywhere: source path escapes the repository: ${subpath}`);
	const key = ref !== void 0 ? `${id}@${ref}` : id;
	return {
		repo: spec.repo,
		...ref !== void 0 ? { ref } : {},
		...subpath !== void 0 ? { path: subpath } : {},
		...spec.rank !== void 0 ? { rank: spec.rank } : {},
		id,
		key,
		url,
		dir,
		scanDir,
		display: subpath !== void 0 ? `${display}/${subpath}` : display
	};
}
/** Strip leading and trailing `/` in linear time (a regex alternation here is quadratic on long runs). */
function trimSlashes(value) {
	let start = 0;
	let end = value.length;
	while (start < end && value.charCodeAt(start) === 47) start += 1;
	while (end > start && value.charCodeAt(end - 1) === 47) end -= 1;
	return value.slice(start, end);
}
function isPlainSegment(segment) {
	return segment.length > 0 && segment !== "." && segment !== ".." && !/[\\/\0]/.test(segment);
}
/** Whether `child` is strictly inside `parent` (both absolute), separator-aware. */
function isInside(parent, child) {
	const rel = relative(parent, child);
	return rel.length > 0 && !rel.startsWith("..") && !isAbsolute(rel);
}
function parseSourceString(input) {
	return { repo: input.trim() };
}
function shortHash(input) {
	return createHash("sha1").update(input).digest("hex").slice(0, 12);
}
let gitAvailable;
/** Whether a usable `git` executable is on PATH (memoised). */
function hasGit() {
	gitAvailable ??= execFileAsync("git", ["--version"]).then(() => true, () => false);
	return gitAvailable;
}
/** Clone or update one source into its cache directory. */
async function syncSource(source, options = {}) {
	if (!await hasGit()) return {
		source,
		status: "skipped",
		error: "git is not installed or not on PATH"
	};
	const timeout = options.timeoutMs ?? 12e4;
	const git = async (args, cwd) => {
		const { stdout } = await execFileAsync("git", [...args], {
			cwd,
			timeout,
			...options.signal !== void 0 ? { signal: options.signal } : {},
			env: {
				...process.env,
				GIT_TERMINAL_PROMPT: "0",
				GIT_LFS_SKIP_SMUDGE: "1"
			},
			maxBuffer: 4194304
		});
		return stdout.trim();
	};
	try {
		if (!await isGitCheckout(source.dir)) {
			await rm(source.dir, {
				recursive: true,
				force: true
			});
			await mkdir(dirname(source.dir), { recursive: true });
			const staging = `${source.dir}.tmp-${process.pid}`;
			await rm(staging, {
				recursive: true,
				force: true
			});
			if (source.ref !== void 0 && SHA_LIKE.test(source.ref)) {
				await mkdir(staging, { recursive: true });
				await git(["init", "-q"], staging);
				await git([
					"remote",
					"add",
					"origin",
					source.url
				], staging);
				await git([
					"fetch",
					"-q",
					"--depth",
					"1",
					"origin",
					source.ref
				], staging);
				await git([
					"checkout",
					"-q",
					"FETCH_HEAD"
				], staging);
			} else {
				const args = [
					"clone",
					"-q",
					"--depth",
					"1",
					"--single-branch"
				];
				if (source.ref !== void 0) args.push("--branch", source.ref);
				args.push(source.url, staging);
				await git(args);
			}
			await rename(staging, source.dir);
			const sha = await git(["rev-parse", "HEAD"], source.dir);
			options.log?.(`skills-anywhere: cloned ${source.display} @ ${sha.slice(0, 12)}`);
			return {
				source,
				status: "cloned",
				sha
			};
		}
		const before = await git(["rev-parse", "HEAD"], source.dir);
		if (source.ref !== void 0 && SHA_LIKE.test(source.ref)) {
			if (before.startsWith(source.ref.toLowerCase()) && !options.force) return {
				source,
				status: "unchanged",
				sha: before
			};
			await git([
				"fetch",
				"-q",
				"--depth",
				"1",
				"origin",
				source.ref
			], source.dir);
			await git([
				"checkout",
				"-q",
				"--detach",
				"FETCH_HEAD"
			], source.dir);
		} else {
			await git([
				"fetch",
				"-q",
				"--depth",
				"1",
				"origin",
				source.ref ?? await defaultBranch(git, source.dir)
			], source.dir);
			await git([
				"checkout",
				"-q",
				"--detach",
				"FETCH_HEAD"
			], source.dir);
		}
		const after = await git(["rev-parse", "HEAD"], source.dir);
		if (after === before) return {
			source,
			status: "unchanged",
			sha: after
		};
		options.log?.(`skills-anywhere: updated ${source.display} ${before.slice(0, 12)} -> ${after.slice(0, 12)}`);
		return {
			source,
			status: "updated",
			sha: after
		};
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		options.log?.(`skills-anywhere: sync of ${source.display} failed: ${firstLine(message)}`);
		return {
			source,
			status: "failed",
			error: firstLine(message)
		};
	}
}
async function defaultBranch(git, dir) {
	try {
		const name = (await git([
			"symbolic-ref",
			"-q",
			"refs/remotes/origin/HEAD"
		], dir)).replace(/^refs\/remotes\/origin\//, "");
		if (name.length > 0) return name;
	} catch {}
	try {
		const remote = await git([
			"ls-remote",
			"--symref",
			"origin",
			"HEAD"
		], dir);
		const match = /^ref: refs\/heads\/(\S+)\s+HEAD/m.exec(remote);
		if (match?.[1] !== void 0) return match[1];
	} catch {}
	return "HEAD";
}
async function isGitCheckout(dir) {
	try {
		return (await stat(join(dir, ".git"))).isDirectory();
	} catch {
		return false;
	}
}
function firstLine(text) {
	return text.split(/\r?\n/).find((line) => line.trim().length > 0)?.trim() ?? text;
}
async function readLock(path) {
	try {
		const parsed = JSON.parse(await readFile(path, "utf8"));
		return typeof parsed === "object" && parsed !== null ? parsed : {};
	} catch {
		return {};
	}
}
async function writeLock(path, lock) {
	await mkdir(dirname(path), { recursive: true });
	await writeFile(path, `${JSON.stringify(lock, null, 2)}\n`);
}
/** Read a `sources.json`; a missing file is an empty list, a malformed one throws. */
async function readSourcesFile(path) {
	let raw;
	try {
		raw = await readFile(path, "utf8");
	} catch (error) {
		if (typeof error === "object" && error !== null && "code" in error && error.code === "ENOENT") return [];
		throw error;
	}
	const parsed = JSON.parse(raw);
	const list = Array.isArray(parsed) ? parsed : parsed?.sources;
	if (!Array.isArray(list)) throw new Error(`skills-anywhere: ${path} must be {"sources": [...]}`);
	return list.map((item) => {
		if (typeof item === "string") return { repo: item };
		if (typeof item === "object" && item !== null && typeof item.repo === "string") return item;
		throw new Error(`skills-anywhere: invalid source entry in ${path}: ${JSON.stringify(item)}`);
	});
}
async function writeSourcesFile(path, sources) {
	const normalized = sources.map((source) => typeof source === "string" ? { repo: source } : source);
	await mkdir(dirname(path), { recursive: true });
	await writeFile(path, `${JSON.stringify({ sources: normalized }, null, 2)}\n`);
}
/** Whether two specs point at the same repository (ignoring ref/path/rank). */
function sameRepository(left, right, cacheDir) {
	try {
		return resolveSource(left, cacheDir).id === resolveSource(right, cacheDir).id;
	} catch {
		return false;
	}
}
//#endregion
//#region src/provider.ts
/**
* The `ctx.skills` provider: builds the root list for a cwd, runs discovery,
* keeps git sources fresh in the background, and watches local roots so the
* dsh catalog refreshes without a restart.
*
* The class has no hard dependency on Cordis so the CLI can drive it directly.
*
* @module
*/
const WATCH_DEBOUNCE_MS = 80;
const MAX_WATCHED_PROJECTS = 32;
const SOURCES_FILE_POLL_MS = 2e3;
/** Skills-anywhere provider for the dsh skill registry. */
var SkillsAnywhereProvider = class {
	config;
	log;
	control;
	name;
	watchers = /* @__PURE__ */ new Map();
	polledFiles = /* @__PURE__ */ new Set();
	watchedProjects = [];
	syncTimer;
	syncing;
	syncQueued;
	/** Project roots the most recent sync run read sources for. */
	lastSyncProjects = /* @__PURE__ */ new Set();
	/** Aborts git processes of in-flight syncs on dispose (or when dsh aborts the provider). */
	abort = new AbortController();
	syncedProjects = /* @__PURE__ */ new Set();
	disposed = false;
	invalidateTimer;
	lastReport;
	lastSync = [];
	/** Catalog state per project root (`''` for no cwd) from the latest `list()`. */
	catalogStates = /* @__PURE__ */ new Map();
	constructor(config, log, control) {
		this.config = config;
		this.log = log;
		this.control = control;
		this.name = config.providerName;
		control?.signal.addEventListener("abort", () => {
			this.dispose();
		}, { once: true });
		if (config.sync && config.syncIntervalMs > 0) {
			this.syncTimer = setInterval(() => {
				this.syncAll();
			}, config.syncIntervalMs);
			this.syncTimer.unref();
		}
		if (config.sync && config.syncOnStart) this.syncAll();
	}
	/** dsh calls this for every catalog refresh; `cwd` selects the project. */
	async list(options = {}) {
		const roots = await this.roots(options.cwd);
		if (this.config.sync && this.config.syncOnStart && options.cwd !== void 0) {
			const projectRoot = await findProjectRoot(options.cwd);
			if (!this.syncedProjects.has(projectRoot)) {
				this.syncedProjects.add(projectRoot);
				this.syncAll(options.cwd);
			}
		}
		if (this.config.watch) await this.watch(roots);
		const report = await discover(roots, {
			dedupe: this.config.dedupe,
			lenient: this.config.lenient,
			excludeSkills: this.config.excludeSkills,
			...options.signal !== void 0 ? { signal: options.signal } : {},
			warn: (message) => this.log.warn(message)
		});
		this.lastReport = report;
		const states = applyCatalogBudget(report.skills, this.config.catalog);
		this.catalogStates.set(options.cwd === void 0 ? "" : await findProjectRoot(options.cwd), states);
		const candidates = report.skills.map((skill) => toCandidate(skill, this.name, states.get(skill.name) ?? "visible"));
		return report.complete ? candidates : {
			candidates,
			complete: false
		};
	}
	/** The configuration currently in force (runtime settings applied). */
	get currentConfig() {
		return this.config;
	}
	/**
	* Replace the runtime-editable part of the configuration (catalog budget,
	* pins, hides, exclusions) and invalidate the catalog so the next `list()`
	* applies it. Everything else (roots, sync, watchers) stays as composed.
	*/
	reconfigure(settings) {
		this.config = {
			...this.config,
			excludeSkills: [...settings.excludeSkills],
			catalog: {
				limit: Math.max(0, Math.floor(settings.catalog.limit)),
				pin: new Set(settings.catalog.pin),
				hide: new Set(settings.catalog.hide)
			}
		};
		this.catalogStates.clear();
		this.invalidate(true);
	}
	/**
	* Everything the web card shows: the latest discovery report for the
	* project containing `cwd` (running one when none exists yet) with the
	* catalog state of every skill and the runtime settings in force.
	*/
	async snapshot(cwd) {
		const key = cwd === void 0 ? "" : await findProjectRoot(cwd);
		if (this.lastReport === void 0 || !this.catalogStates.has(key)) await this.list(cwd === void 0 ? {} : { cwd });
		const report = this.lastReport;
		const states = this.catalogStates.get(key) ?? this.catalogStates.get("") ?? /* @__PURE__ */ new Map();
		const { catalog, excludeSkills } = this.config;
		const skills = (report?.skills ?? []).map((skill) => {
			const extra = skill.metadata.skillsAnywhere;
			return {
				name: skill.name,
				description: skill.description,
				origin: originLabel(skill.origin),
				group: originGroup(skill.origin),
				path: skill.path,
				state: states.get(skill.name) ?? "visible",
				authorDisabled: !skill.invocation.modelInvocable,
				...extra?.renamedFrom !== void 0 ? { renamedFrom: extra.renamedFrom } : {},
				pinned: catalog.pin.has(skill.name),
				hidden: catalog.hide.has(skill.name),
				warnings: skill.warnings
			};
		});
		return {
			skills,
			dropped: (report?.dropped ?? []).map((entry) => ({
				name: entry.skill.name,
				path: entry.skill.path,
				reason: entry.reason,
				winner: entry.winner.name
			})),
			invalid: (report?.invalid ?? []).map((entry) => ({
				path: entry.path,
				reason: entry.reason
			})),
			roots: (report?.roots ?? []).map((entry) => ({
				label: entry.root.label,
				path: entry.root.path,
				exists: entry.exists,
				count: entry.count
			})),
			complete: report?.complete ?? true,
			catalog: {
				limit: catalog.limit,
				pin: [...catalog.pin],
				hide: [...catalog.hide]
			},
			excludeSkills: [...excludeSkills],
			listed: skills.filter((skill) => skill.state === "visible").length
		};
	}
	/**
	* Catalog state of one published skill as of the latest `list()` for the
	* project containing `cwd`. `hidden` means the budget kept it out of the
	* model catalog; `disabled` means the skill's own frontmatter did.
	*/
	async catalogState(name, cwd) {
		const key = cwd === void 0 ? "" : await findProjectRoot(cwd);
		return (this.catalogStates.get(key) ?? this.catalogStates.get(""))?.get(name);
	}
	/** Re-read the winning file so edits are always reflected. */
	async get(candidate, options = {}) {
		const locator = candidate.locator;
		let raw;
		try {
			options.signal?.throwIfAborted();
			const bytes = await readSkillBytes(locator.path);
			options.signal?.throwIfAborted();
			raw = new TextDecoder("utf-8", {
				fatal: true,
				ignoreBOM: true
			}).decode(bytes);
		} catch (error) {
			options.signal?.throwIfAborted();
			if (isAbsent(error)) return void 0;
			throw error;
		}
		const parsed = parseSkillMarkdown(raw, {
			fallbackName: candidate.name,
			lenient: this.config.lenient
		});
		if (!parsed.ok) {
			this.log.warn(`skills-anywhere: ${locator.path} became unreadable: ${parsed.reason}`);
			return;
		}
		return {
			name: candidate.name,
			description: parsed.skill.description,
			...parsed.skill.whenToUse !== void 0 ? { whenToUse: parsed.skill.whenToUse } : {},
			invocation: {
				modelInvocable: candidate.invocation.modelInvocable && parsed.skill.invocation.modelInvocable,
				userInvocable: candidate.invocation.userInvocable && parsed.skill.invocation.userInvocable
			},
			source: candidate.source,
			provider: this.name,
			resourceBase: {
				kind: "directory",
				path: locator.directory
			},
			path: locator.path,
			metadata: {
				...parsed.skill.metadata,
				...candidate.metadata,
				skillsAnywhere: {
					...candidate.metadata?.skillsAnywhere,
					authorInvocation: parsed.skill.invocation
				}
			},
			content: parsed.skill.content
		};
	}
	/** Report from the most recent `list()`; the CLI uses it for diagnostics. */
	report() {
		return this.lastReport;
	}
	/** Results of the most recent source sync. */
	syncResults() {
		return this.lastSync;
	}
	/** Every configured source (config + files) for a cwd. */
	async sources(cwd) {
		return this.collectSources(cwd === void 0 ? [] : [await findProjectRoot(cwd)]);
	}
	/** Config- and user-level sources plus the project files of `projectRoots`. */
	async collectSources(projectRoots) {
		const specs = [...this.config.sources];
		if (this.config.sourcesFiles) {
			specs.push(...await this.readSources(this.config.userSourcesFile));
			for (const projectRoot of new Set(projectRoots)) specs.push(...await this.readSources(projectSourcesFile(projectRoot)));
		}
		const resolved = [];
		const seen = /* @__PURE__ */ new Set();
		for (const spec of specs) try {
			const source = resolveSource(spec, this.config.cacheDir);
			const key = `${source.id}\0${source.ref ?? ""}\0${source.path ?? ""}`;
			if (seen.has(key)) continue;
			seen.add(key);
			resolved.push(source);
		} catch (error) {
			this.log.warn(String(error instanceof Error ? error.message : error));
		}
		return resolved;
	}
	/**
	* Clone or refresh every source. Concurrent calls share one run; a call that
	* names a project (or forces) while a run is in flight queues one follow-up
	* run, because the in-flight run read its source list before this request.
	*/
	syncAll(cwd, options = {}) {
		if (this.syncing !== void 0) {
			if (cwd === void 0 && options.force !== true) return this.syncing;
			this.syncQueued ??= this.syncing.catch(() => []).then(async (results) => {
				this.syncQueued = void 0;
				if (this.disposed) return results;
				if (cwd !== void 0 && options.force !== true) {
					const projectRoot = await findProjectRoot(cwd);
					if (this.lastSyncProjects.has(projectRoot)) return results;
					if ((await this.readSources(projectSourcesFile(projectRoot))).length === 0) return results;
				}
				return this.syncAll(cwd, options);
			});
			return this.syncQueued;
		}
		this.syncing = this.runSync(cwd, options).finally(() => {
			this.syncing = void 0;
		});
		return this.syncing;
	}
	async runSync(cwd, options) {
		if (this.disposed) return [];
		const projectRoots = new Set(this.syncedProjects);
		if (cwd !== void 0) projectRoots.add(await findProjectRoot(cwd));
		this.lastSyncProjects = projectRoots;
		const sources = await this.collectSources(projectRoots);
		if (sources.length === 0) return [];
		const lock = await readLock(this.config.lockFile);
		const results = [];
		let changed = false;
		for (const source of sources) {
			if (this.disposed) break;
			const result = await syncSource(source, {
				...options.force !== void 0 ? { force: options.force } : {},
				timeoutMs: this.config.syncTimeoutMs,
				signal: this.abort.signal,
				log: (message) => this.log.info(message)
			});
			results.push(result);
			if (result.status === "cloned" || result.status === "updated") changed = true;
			if (result.sha !== void 0) lock[source.key] = {
				url: source.url,
				...source.ref !== void 0 ? { ref: source.ref } : {},
				sha: result.sha,
				syncedAt: (/* @__PURE__ */ new Date()).toISOString()
			};
		}
		this.lastSync = results;
		try {
			await writeLock(this.config.lockFile, lock);
		} catch (error) {
			this.log.warn(`skills-anywhere: could not write ${this.config.lockFile}: ${String(error)}`);
		}
		if (changed) this.invalidate();
		return results;
	}
	/** Build the ordered root list for one cwd. */
	async roots(cwd) {
		const { config } = this;
		const roots = [];
		const projectRoot = cwd !== void 0 ? await findProjectRoot(cwd) : void 0;
		if (config.agents && projectRoot !== void 0) for (const agent of AGENTS) {
			if (agent.project === void 0 || config.excludeAgents.has(agent.id)) continue;
			roots.push({
				path: join(projectRoot, agent.project),
				project: projectRoot,
				source: "anywhere-project",
				rank: config.ranks.project,
				mode: "flat",
				origin: {
					kind: "agent",
					agent: agent.id,
					scope: "project"
				},
				label: `${agent.id} (project)`
			});
		}
		if (projectRoot !== void 0) for (const dir of config.extraProjectDirs) roots.push({
			path: join(projectRoot, dir),
			project: projectRoot,
			source: "anywhere-project",
			rank: config.ranks.project,
			mode: "flat",
			origin: {
				kind: "custom",
				scope: "project"
			},
			label: `${dir} (project)`
		});
		if (config.agents) {
			const seen = /* @__PURE__ */ new Set();
			for (const agent of AGENTS) {
				if (agent.user === void 0 || config.excludeAgents.has(agent.id)) continue;
				const path = join(config.home, agent.user);
				if (seen.has(path)) continue;
				seen.add(path);
				roots.push({
					path,
					source: "anywhere-user",
					rank: config.ranks.user,
					mode: "flat",
					origin: {
						kind: "agent",
						agent: agent.id,
						scope: "user"
					},
					label: `${agent.id} (user)`
				});
			}
		}
		for (const dir of config.extraUserDirs) roots.push({
			path: dir,
			source: "anywhere-user",
			rank: config.ranks.user,
			mode: "flat",
			origin: {
				kind: "custom",
				scope: "user"
			},
			label: `${dir} (user)`
		});
		if (config.claudePlugins) {
			const base = join(config.home, ".claude", "plugins");
			roots.push({
				path: join(base, "marketplaces"),
				source: "anywhere-claude-plugins",
				rank: config.ranks.claudePlugins,
				mode: "nested",
				maxDepth: Math.max(config.maxDepth, 6),
				origin: { kind: "claude-plugins" },
				label: "claude-code marketplaces"
			});
			roots.push({
				path: join(base, "cache"),
				source: "anywhere-claude-plugins",
				rank: config.ranks.claudePlugins,
				mode: "nested",
				maxDepth: Math.max(config.maxDepth, 7),
				origin: { kind: "claude-plugins" },
				label: "claude-code plugin cache"
			});
		}
		for (const source of await this.sources(cwd)) roots.push({
			path: source.scanDir,
			source: "anywhere-source",
			rank: source.rank ?? config.ranks.sources,
			mode: "nested",
			maxDepth: config.maxDepth,
			origin: {
				kind: "source",
				repo: source.display
			},
			label: `source ${source.display}`
		});
		return roots;
	}
	/** Stop timers and watchers. Safe to call more than once. */
	async dispose() {
		if (this.disposed) return;
		this.disposed = true;
		if (this.syncTimer !== void 0) clearInterval(this.syncTimer);
		if (this.invalidateTimer !== void 0) clearTimeout(this.invalidateTimer);
		for (const file of this.polledFiles) unwatchFile(file);
		this.polledFiles.clear();
		const closing = [...this.watchers.values()].map((watcher) => watcher.close().catch(() => void 0));
		this.watchers.clear();
		this.abort.abort();
		await Promise.all([
			...closing,
			this.syncing?.catch(() => void 0),
			this.syncQueued?.catch(() => void 0)
		]);
	}
	async readSources(path) {
		try {
			const sources = await readSourcesFile(path);
			if (this.config.watch) this.pollFile(path);
			return sources;
		} catch (error) {
			this.log.warn(String(error instanceof Error ? error.message : error));
			return [];
		}
	}
	invalidate(immediately = false) {
		if (this.disposed || this.control === void 0) return;
		if (this.invalidateTimer !== void 0) clearTimeout(this.invalidateTimer);
		if (immediately) {
			this.invalidateTimer = void 0;
			this.control.invalidate();
			return;
		}
		this.invalidateTimer = setTimeout(() => {
			this.invalidateTimer = void 0;
			this.control?.invalidate();
		}, WATCH_DEBOUNCE_MS);
		this.invalidateTimer.unref();
	}
	/** Watch existing flat roots (bounded per project) and the sources files. */
	async watch(roots) {
		if (this.disposed) return;
		for (const root of roots) {
			if (root.mode !== "flat") continue;
			if (this.watchers.has(root.path)) continue;
			if (root.origin.scope === "project" && !this.admitProject(root.project ?? root.path)) continue;
			try {
				const watcher = chokidar.watch(root.path, {
					depth: 1,
					ignoreInitial: true,
					persistent: true,
					followSymlinks: true,
					awaitWriteFinish: {
						stabilityThreshold: 150,
						pollInterval: 50
					}
				});
				watcher.on("all", (_event, path) => {
					if (/(?:^|[\\/])(?:SKILL\.md|[^\\/]+\.md)$/.test(path) || !/\.[^\\/]+$/.test(path)) this.invalidate();
				});
				watcher.on("error", () => {});
				this.watchers.set(root.path, watcher);
			} catch {}
		}
		if (this.config.claudePlugins) {
			this.pollFile(join(this.config.home, ".claude", "plugins", "known_marketplaces.json"));
			this.pollFile(join(this.config.home, ".claude", "plugins", "installed_plugins.json"));
		}
	}
	/** Bound the number of *projects* (not directories) whose roots are watched. */
	admitProject(project) {
		if (this.watchedProjects.includes(project)) return true;
		if (this.watchedProjects.length >= MAX_WATCHED_PROJECTS) return false;
		this.watchedProjects.push(project);
		return true;
	}
	pollFile(path) {
		if (this.disposed || this.polledFiles.has(path)) return;
		this.polledFiles.add(path);
		watchFile(path, {
			persistent: false,
			interval: SOURCES_FILE_POLL_MS
		}, (current, previous) => {
			if (current.mtimeMs !== previous.mtimeMs || current.size !== previous.size) {
				this.invalidate();
				if (path.endsWith("sources.json") || path.endsWith("skills-anywhere.json")) this.syncAll();
			}
		});
	}
};
/** Preserve author invocation metadata when a catalog budget hides a candidate. */
function toCandidate(skill, provider, state) {
	const locator = {
		path: skill.path,
		directory: skill.directory
	};
	const extra = skill.metadata.skillsAnywhere;
	return {
		name: skill.name,
		description: skill.description,
		...skill.whenToUse !== void 0 ? { whenToUse: skill.whenToUse } : {},
		invocation: state === "hidden" ? {
			modelInvocable: false,
			userInvocable: skill.invocation.userInvocable
		} : skill.invocation,
		provider,
		source: skill.source,
		rank: skill.rank,
		locator,
		path: skill.path,
		resourceBase: {
			kind: "directory",
			path: skill.directory
		},
		metadata: {
			...skill.metadata,
			skillsAnywhere: {
				...extra,
				catalog: state,
				authorInvocation: skill.invocation
			}
		}
	};
}
function isAbsent(error) {
	return typeof error === "object" && error !== null && "code" in error && (error.code === "ENOENT" || error.code === "ENOTDIR");
}
//#endregion
export { Config as _, resolveSource as a, resolveConfig as b, writeSourcesFile as c, originLabel as d, discover as f, readSkillBytes as g, agentById as h, readSourcesFile as i, applyCatalogBudget as l, AGENTS as m, hasGit as n, sameRepository as o, findProjectRoot as p, readLock as r, syncSource as s, SkillsAnywhereProvider as t, originGroup as u, DEFAULT_RANKS as v, projectSourcesFile as y };
