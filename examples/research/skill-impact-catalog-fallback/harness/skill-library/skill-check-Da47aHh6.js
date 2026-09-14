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
		}))
	};
}
//#endregion
export { parseSkillMarkdown as a, normalizeSkillName as i, checkSkill as n, splitFrontmatter as o, isSkillName as r, MAX_SKILL_BYTES as t };
