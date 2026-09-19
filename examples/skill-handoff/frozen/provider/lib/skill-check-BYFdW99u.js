import { parse } from "yaml";
const MAX_DESCRIPTION_LENGTH = 1024;
const SKILL_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const FRONTMATTER_OPEN = /^﻿?---[ \t]*\r?\n/;
const FRONTMATTER_CLOSE = /^(?:---|\.\.\.)[ \t]*$/;
/** Whether a string is a valid Agent Skills / dsh skill name. */
function isSkillName(name) {
	return name.length > 0 && name.length <= 64 && SKILL_NAME.test(name);
}
/**
* Normalise an arbitrary string into a valid skill name, or `undefined` when
* nothing usable remains (for example an empty or all-punctuation string).
*/
function normalizeSkillName(input) {
	let name = input.normalize("NFKD").replace(/\p{M}+/gu, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
	if (name.length > 64) name = name.slice(0, 64).replace(/-+$/g, "");
	return isSkillName(name) ? name : void 0;
}
/** Split a Markdown document into YAML frontmatter text and body. */
function splitFrontmatter(raw) {
	const open = FRONTMATTER_OPEN.exec(raw);
	if (open === null) return void 0;
	const lines = raw.slice(open[0].length).split(/\r?\n/);
	for (let index = 0; index < lines.length; index += 1) if (FRONTMATTER_CLOSE.test(lines[index] ?? "")) return {
		frontmatter: lines.slice(0, index).join("\n"),
		body: lines.slice(index + 1).join("\n")
	};
}
/** Parse one SKILL.md (or flat `<name>.md`) document. */
function parseSkillMarkdown(raw, options) {
	const lenient = options.lenient ?? true;
	const warnings = [];
	const split = splitFrontmatter(raw);
	if (split === void 0) {
		if (!lenient) return {
			ok: false,
			reason: "missing YAML frontmatter"
		};
		return finish({}, raw, options, warnings, "missing YAML frontmatter; derived name and description");
	}
	let data;
	try {
		data = split.frontmatter.trim().length === 0 ? {} : parse(split.frontmatter);
	} catch (error) {
		return {
			ok: false,
			reason: `invalid YAML frontmatter: ${String(error)}`
		};
	}
	if (data === null || data === void 0) data = {};
	if (typeof data !== "object" || Array.isArray(data)) return {
		ok: false,
		reason: "frontmatter must be a YAML mapping"
	};
	return finish(data, split.body, options, warnings);
}
function finish(data, body, options, warnings, initialWarning) {
	const lenient = options.lenient ?? true;
	if (initialWarning !== void 0) warnings.push(initialWarning);
	const rawName = stringField(data, "name");
	let name;
	if (rawName !== void 0 && isSkillName(rawName)) name = rawName;
	else if (!lenient) return {
		ok: false,
		reason: rawName === void 0 ? "frontmatter requires name" : `invalid skill name "${rawName}"`
	};
	else if (rawName !== void 0) {
		name = normalizeSkillName(rawName);
		if (name !== void 0) warnings.push(`name "${rawName}" normalised to "${name}"`);
	}
	if (name === void 0) {
		name = normalizeSkillName(options.fallbackName);
		if (name === void 0) return {
			ok: false,
			reason: `no usable skill name (frontmatter: ${JSON.stringify(rawName)}, directory: ${JSON.stringify(options.fallbackName)})`
		};
		warnings.push(`name missing or invalid; using "${name}" from the directory`);
	}
	let description = stringField(data, "description");
	if (description === void 0) {
		if (!lenient) return {
			ok: false,
			reason: "frontmatter requires description"
		};
		description = firstParagraph(body);
		if (description === void 0) return {
			ok: false,
			reason: "no description in frontmatter and no body text to derive one from"
		};
		warnings.push("description missing; derived from the first paragraph");
	}
	if (description.length > 1024) {
		description = description.slice(0, MAX_DESCRIPTION_LENGTH);
		warnings.push(`description longer than ${MAX_DESCRIPTION_LENGTH} characters; truncated`);
	}
	let invocation;
	try {
		invocation = parseInvocation(data, lenient, warnings);
	} catch (error) {
		return {
			ok: false,
			reason: String(error instanceof Error ? error.message : error)
		};
	}
	const metadata = collectMetadata(data);
	const whenToUse = stringField(data, "whenToUse") ?? stringField(data, "when-to-use");
	return {
		ok: true,
		skill: {
			name,
			description,
			...whenToUse !== void 0 ? { whenToUse } : {},
			invocation,
			metadata,
			content: body.trim(),
			warnings
		}
	};
}
const KNOWN_KEYS = /* @__PURE__ */ new Set([
	"name",
	"description",
	"whenToUse",
	"when-to-use",
	"metadata",
	"license",
	"compatibility",
	"allowed-tools",
	"disable-model-invocation",
	"user-invocable",
	"disableModelInvocation",
	"modelInvocable",
	"userInvocable"
]);
function collectMetadata(data) {
	const metadata = {};
	const declared = data.metadata;
	if (typeof declared === "object" && declared !== null && !Array.isArray(declared)) Object.assign(metadata, declared);
	for (const key of ["license", "compatibility"]) {
		const value = stringField(data, key);
		if (value !== void 0) metadata[key] = value;
	}
	const allowedTools = data["allowed-tools"];
	if (typeof allowedTools === "string" && allowedTools.trim().length > 0) metadata.allowedTools = allowedTools.trim().split(/\s+/);
	else if (Array.isArray(allowedTools)) metadata.allowedTools = allowedTools.filter((tool) => typeof tool === "string");
	const extra = {};
	for (const [key, value] of Object.entries(data)) {
		if (KNOWN_KEYS.has(key)) continue;
		if (value === null || value === void 0) continue;
		if (typeof value === "object" && !Array.isArray(value)) continue;
		extra[key] = value;
	}
	if (Object.keys(extra).length > 0) metadata.frontmatter = extra;
	return metadata;
}
function parseInvocation(data, lenient, warnings) {
	let disableModel = readBoolean(data, "disable-model-invocation");
	let userInvocable = readBoolean(data, "user-invocable");
	for (const [legacy, apply] of [
		["disableModelInvocation", (value) => {
			disableModel ??= value;
		}],
		["modelInvocable", (value) => {
			disableModel ??= !value;
		}],
		["userInvocable", (value) => {
			userInvocable ??= value;
		}]
	]) {
		if (!Object.hasOwn(data, legacy)) continue;
		if (!lenient) throw new Error(`frontmatter field "${legacy}" is unsupported`);
		const value = readBoolean(data, legacy);
		if (value !== void 0) {
			apply(value);
			warnings.push(`legacy frontmatter field "${legacy}" accepted`);
		}
	}
	return {
		modelInvocable: disableModel !== true,
		userInvocable: userInvocable !== false
	};
}
function readBoolean(data, key) {
	if (!Object.hasOwn(data, key)) return void 0;
	const value = data[key];
	if (typeof value === "boolean") return value;
	if (value === 1 || value === "1") return true;
	if (value === 0 || value === "0") return false;
	if (typeof value === "string") switch (value.trim().toLowerCase()) {
		case "true":
		case "yes":
		case "on": return true;
		case "false":
		case "no":
		case "off": return false;
	}
	throw new TypeError(`frontmatter field "${key}" must be a boolean`);
}
function stringField(data, key) {
	const value = data[key];
	if (typeof value === "number") return String(value);
	if (typeof value !== "string") return void 0;
	const trimmed = value.trim();
	return trimmed.length > 0 ? trimmed : void 0;
}
/** First non-heading, non-empty paragraph of a Markdown body, flattened to one line. */
function firstParagraph(body) {
	const blocks = body.replace(/```[\s\S]*?(?:```|$)/g, "").replace(/~~~[\s\S]*?(?:~~~|$)/g, "").replace(/<!--[\s\S]*?-->/g, "").replace(/<!--[\s\S]*$/, "").split(/\r?\n\s*\r?\n/);
	for (const block of blocks) {
		const lines = block.split(/\r?\n/).map((line) => line.trim()).filter((line) => line.length > 0);
		if (lines.length === 0) continue;
		if (lines.every((line) => /^(#{1,6}\s|[-*_]{3,}$|```|<!--)/.test(line))) continue;
		const text = lines.filter((line) => !/^#{1,6}\s/.test(line)).join(" ").replace(/[*_`>]+/g, "").replace(/\s+/g, " ").trim();
		if (text.length > 0) return text.slice(0, MAX_DESCRIPTION_LENGTH);
	}
}
//#endregion
//#region src/skill-surface.ts
const URL_PATTERN = /\bhttps?:\/\/[^\s<>"'`)\]}]+/gi;
/** Trailing punctuation belongs to the prose, not to the URL. */
function trimPunctuation(url) {
	return url.replace(/[.,;:!?]+$/, "");
}
/**
* Whether a reference names an immutable revision.
*
* Only recognize commit positions on known source hosts. A random hex segment
* or a digest fragment on an arbitrary host does not constrain the response.
* Fragments are not even sent to an HTTP server. Queries can change routing.
*/
function isPinned(url) {
	let parsed;
	try {
		parsed = new URL(url);
	} catch {
		return false;
	}
	if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.port || parsed.search) return false;
	const segments = parsed.pathname.split("/").slice(1);
	const commit = (value) => /^[a-f0-9]{40}$/i.test(value ?? "");
	const file = (start) => segments.length > start && segments.slice(start).every(Boolean);
	if (parsed.hostname === "raw.githubusercontent.com") return !!segments[0] && !!segments[1] && commit(segments[2]) && file(3);
	if (parsed.hostname === "github.com") return !!segments[0] && !!segments[1] && [
		"blob",
		"raw",
		"tree"
	].includes(segments[2] ?? "") && commit(segments[3]) && file(4);
	if (parsed.hostname === "huggingface.co") {
		const offset = ["datasets", "spaces"].includes(segments[0] ?? "") ? 1 : 0;
		return !!segments[offset] && !!segments[offset + 1] && ["resolve", "blob"].includes(segments[offset + 2] ?? "") && commit(segments[offset + 3]) && file(offset + 4);
	}
	return false;
}
/**
* Read the reachable surface of a skill body.
*
* Bounded and local: no request is made, nothing is resolved, and the body is
* scanned once. Callers get the same answer offline as online, which is what
* makes the result usable in CI.
*/
function readSkillSurface(body, declaredTools = []) {
	const byHost = /* @__PURE__ */ new Map();
	for (const match of body.matchAll(URL_PATTERN)) {
		const url = trimPunctuation(match[0]);
		let host;
		try {
			host = new URL(url).host.toLowerCase();
		} catch {
			continue;
		}
		if (host.length === 0) continue;
		const entry = byHost.get(host) ?? {
			urls: /* @__PURE__ */ new Set(),
			pinned: true
		};
		entry.urls.add(url);
		entry.pinned = entry.pinned && isPinned(url);
		byHost.set(host, entry);
	}
	return {
		schema: "skills-anywhere-surface-1",
		externalSources: [...byHost.entries()].map(([host, entry]) => ({
			host,
			urls: [...entry.urls].toSorted(),
			pinned: entry.pinned
		})).toSorted((left, right) => left.host.localeCompare(right.host)),
		declaredTools: [...declaredTools],
		notAssessed: [
			"AST01 Malicious Skills: no verdict on intent; reading a file cannot establish it.",
			"AST08 Poor Scanning: this enumerates sources and declarations, and does not pattern-match for payloads.",
			"AST06 Weak Isolation: a property of how the agent runs, not of the file."
		]
	};
}
//#endregion
//#region src/skill-check.ts
const MAX_SKILL_BYTES = 131072;
const encoder = new TextEncoder();
function summarize(result) {
	if (!result.ok) return result;
	const { name, description, invocation, warnings, metadata, content } = result.skill;
	return {
		ok: true,
		name,
		description,
		invocation,
		warnings,
		metadataKeys: Object.keys(metadata).toSorted(),
		bodyBytes: encoder.encode(content).length
	};
}
/** Read the reachable surface from whichever parse succeeded, if either did. */
function surfaceOf(result) {
	if (!result.ok) return readSkillSurface("", []);
	const declared = result.skill.metadata.allowedTools;
	return readSkillSurface(result.skill.content, Array.isArray(declared) ? declared : []);
}
/** A bounded, local comparison of the provider's two parsing modes. */
function checkSkill(raw, fallbackName) {
	const bytes = encoder.encode(raw).length;
	if (bytes > 131072) throw new Error("Choose a SKILL.md of 128 KiB or less.");
	if (fallbackName.length > 128) throw new Error("Use a directory name of 128 characters or less.");
	return {
		schema: "skills-anywhere-local-check-1",
		input: {
			bytes,
			fallbackName
		},
		strict: summarize(parseSkillMarkdown(raw, {
			fallbackName,
			lenient: false
		})),
		lenient: summarize(parseSkillMarkdown(raw, {
			fallbackName,
			lenient: true
		})),
		surface: surfaceOf(parseSkillMarkdown(raw, {
			fallbackName,
			lenient: true
		}))
	};
}
//#endregion
export { parseSkillMarkdown as a, normalizeSkillName as i, checkSkill as n, splitFrontmatter as o, isSkillName as r, MAX_SKILL_BYTES as t };
