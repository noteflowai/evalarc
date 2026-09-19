import { i as validateManifest, n as MAX_MANIFEST_BYTES, r as compareManifests, t as readBundle } from "./skill-bundle-2OVsba66.js";
import { isAbsolute, relative, resolve } from "node:path";
import { constants } from "node:fs";
import { open, realpath } from "node:fs/promises";
//#region src/bundle-cli.ts
async function readManifest(path) {
	const handle = await open(path, constants.O_RDONLY | (constants.O_NONBLOCK ?? 0));
	try {
		const stat = await handle.stat();
		if (!stat.isFile() || stat.size > 1048576) throw new Error("Choose a regular manifest file of at most 1 MiB.");
		const buffer = Buffer.alloc(MAX_MANIFEST_BYTES + 1);
		let size = 0;
		while (size < buffer.length) {
			const { bytesRead } = await handle.read(buffer, size, buffer.length - size, null);
			if (!bytesRead) break;
			size += bytesRead;
		}
		if (size > 1048576) throw new Error("Manifest exceeds 1 MiB.");
		return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(buffer.subarray(0, size)));
	} finally {
		await handle.close();
	}
}
async function bundleCommand(directory, options) {
	try {
		const root = resolve(options.cwd, directory);
		let expected;
		if (options.against !== void 0) {
			const path = resolve(options.cwd, options.against);
			const rel = relative(await realpath(root), await realpath(path));
			if (!isAbsolute(rel) && rel !== ".." && !rel.startsWith("../") && !rel.startsWith("..\\")) throw new Error("Keep the review manifest outside the skill directory.");
			expected = await validateManifest(await readManifest(path));
		}
		const { manifest } = await readBundle(root);
		const comparison = expected === void 0 ? void 0 : compareManifests(expected, manifest);
		const result = comparison === void 0 ? manifest : {
			...comparison,
			manifest
		};
		if (options.json) console.log(JSON.stringify(result, null, 2));
		else {
			console.log(`Bundle SHA-256: ${manifest.sha256}\n${manifest.files.length} files, ${manifest.total_bytes} bytes`);
			if (comparison) {
				console.log(comparison.matches ? "Matches the reviewed bundle." : "Bundle differs from the reviewed inventory.");
				for (const kind of [
					"added",
					"removed",
					"changed"
				]) for (const path of comparison[kind]) console.log(`${kind.toUpperCase()} ${JSON.stringify(path)}`);
			}
			console.log("File paths and contents only; no execution, author authentication or external dependency verification.");
		}
		return comparison && !comparison.matches ? 1 : 0;
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		if (options.json) console.log(JSON.stringify({
			schema: "skills-anywhere-bundle-error-1",
			error: message
		}));
		else console.error(`Bundle check failed: ${JSON.stringify(message)}`);
		return 2;
	}
}
//#endregion
export { bundleCommand };
