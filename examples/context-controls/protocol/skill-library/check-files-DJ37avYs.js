import { g as readSkillBytes } from "./provider-DIndg2HA.js";
import { n as checkSkill } from "./skill-check-BYFdW99u.js";
import { createRequire } from "node:module";
import { basename, dirname, extname, resolve } from "node:path";
import { createHash } from "node:crypto";
//#region src/check-files.ts
/** Read only explicitly named files; do not discover, sync or execute skills. */
async function checkFiles(paths, options) {
	const pkg = createRequire(import.meta.url)("../package.json");
	const mode = options.lenient ? "lenient" : "strict";
	const files = [];
	for (const input of paths) try {
		const path = resolve(options.cwd, input);
		const bytes = await readSkillBytes(path);
		const raw = new TextDecoder("utf-8", {
			fatal: true,
			ignoreBOM: true
		}).decode(bytes);
		const fallback = basename(path) === "SKILL.md" ? basename(dirname(path)) : basename(path, extname(path));
		const report = checkSkill(raw, fallback);
		const selected = report[mode];
		const unpinned = report.surface.externalSources.filter((source) => !source.pinned).map((source) => source.host);
		const passed = selected.ok && (!options.failOnRepair || selected.warnings.length === 0) && (!options.requirePinnedSources || unpinned.length === 0);
		files.push({
			path: input,
			status: passed ? "passed" : "failed",
			sha256: createHash("sha256").update(bytes).digest("hex"),
			report,
			...options.requirePinnedSources && unpinned.length > 0 ? { unpinnedSources: unpinned } : {}
		});
	} catch (error) {
		const message = error instanceof TypeError && "code" in error && error.code === "ERR_ENCODING_INVALID_ENCODED_DATA" ? "Input is not valid UTF-8." : error instanceof Error ? error.message : String(error);
		files.push({
			path: input,
			status: "input_error",
			error: message
		});
	}
	const counts = {
		passed: files.filter((file) => file.status === "passed").length,
		failed: files.filter((file) => file.status === "failed").length,
		inputErrors: files.filter((file) => file.status === "input_error").length
	};
	return {
		schema: "skills-anywhere-file-check-1",
		tool: {
			name: "dsh-skills-anywhere",
			version: pkg.version
		},
		mode,
		failOnRepair: options.failOnRepair,
		requirePinnedSources: options.requirePinnedSources,
		files,
		counts,
		exitCode: counts.inputErrors > 0 ? 2 : counts.failed > 0 ? 1 : 0,
		scope: "Provider parsing, plus an enumeration of external sources and declared tools. No verdict on intent, no payload scanning, no script or client compatibility verification."
	};
}
//#endregion
export { checkFiles };
