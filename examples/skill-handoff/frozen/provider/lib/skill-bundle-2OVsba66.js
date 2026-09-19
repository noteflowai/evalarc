import { t as MAX_SKILL_BYTES } from "./skill-check-BYFdW99u.js";
import { join, resolve } from "node:path";
import { constants } from "node:fs";
import { lstat, open, opendir, realpath } from "node:fs/promises";
import { createHash } from "node:crypto";
const MAX_BUNDLE_BYTES = 33554432;
const MAX_BUNDLE_FILE_BYTES = 16777216;
const MAX_MANIFEST_BYTES = 1048576;
const BUNDLE_SCHEMA = "skills-anywhere-bundle-1";
const digestPattern = /^[a-f0-9]{64}$/;
function validBundlePath(path) {
	const parts = path.split("/");
	return path.isWellFormed() && new TextEncoder().encode(path).length <= 1024 && !/[\\:\x00-\x1f\x7f\ufffd]/.test(path) && parts.length <= 12 && parts.every((part) => part !== "" && part !== "." && part !== "..");
}
function objectKeys(value, keys) {
	return value !== null && typeof value === "object" && !Array.isArray(value) && Object.keys(value).toSorted().join(",") === keys.toSorted().join(",");
}
/** Canonical UTF-8 JSON tuple: schema followed by [path, bytes, sha256] rows. */
async function makeManifest(files) {
	if (files.length < 1 || files.length > 512) throw new Error("A bundle needs 1–512 files.");
	let previous = "";
	let total = 0;
	const paths = /* @__PURE__ */ new Set();
	for (const file of files) {
		if (!objectKeys(file, [
			"path",
			"bytes",
			"sha256"
		]) || typeof file.path !== "string" || !validBundlePath(file.path) || file.path <= previous || typeof file.bytes !== "number" || !Number.isSafeInteger(file.bytes) || file.bytes < 0 || file.bytes > 16777216 || typeof file.sha256 !== "string" || !digestPattern.test(file.sha256)) throw new Error("Invalid bundle file: require unique sorted relative paths, bounded byte counts and SHA-256.");
		const parents = file.path.split("/");
		parents.pop();
		while (parents.length) {
			if (paths.has(parents.join("/"))) throw new Error("A bundle file cannot also be a directory.");
			parents.pop();
		}
		if (file.path === "SKILL.md" && file.bytes > 131072) throw new Error("SKILL.md exceeds 128 KiB.");
		paths.add(file.path);
		previous = file.path;
		total += file.bytes;
	}
	if (!files.some((file) => file.path === "SKILL.md")) throw new Error("A bundle must contain SKILL.md.");
	if (total > 33554432) throw new Error("A bundle must not exceed 32 MiB.");
	const payload = JSON.stringify([BUNDLE_SCHEMA, files.map((file) => [
		file.path,
		file.bytes,
		file.sha256
	])]);
	const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(payload));
	return {
		schema: BUNDLE_SCHEMA,
		sha256: Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join(""),
		total_bytes: total,
		files: files.map((file) => ({
			path: file.path,
			bytes: file.bytes,
			sha256: file.sha256
		}))
	};
}
/** A received manifest must agree with its own inventory and digest. */
async function validateManifest(value) {
	if (!objectKeys(value, [
		"schema",
		"sha256",
		"total_bytes",
		"files"
	]) || value.schema !== "skills-anywhere-bundle-1" || !Array.isArray(value.files)) throw new Error("Expected a skills-anywhere-bundle-1 manifest.");
	const computed = await makeManifest(value.files);
	if (value.sha256 !== computed.sha256 || value.total_bytes !== computed.total_bytes) throw new Error("Manifest digest or total bytes disagrees with its inventory.");
	return computed;
}
function compareManifests(expected, actual) {
	const before = new Map(expected.files.map((file) => [file.path, file]));
	const after = new Map(actual.files.map((file) => [file.path, file]));
	return {
		schema: "skills-anywhere-bundle-comparison-1",
		matches: expected.sha256 === actual.sha256,
		expected_sha256: expected.sha256,
		actual_sha256: actual.sha256,
		added: actual.files.filter((file) => !before.has(file.path)).map((file) => file.path),
		removed: expected.files.filter((file) => !after.has(file.path)).map((file) => file.path),
		changed: actual.files.filter((file) => {
			const old = before.get(file.path);
			return old !== void 0 && (old.sha256 !== file.sha256 || old.bytes !== file.bytes);
		}).map((file) => file.path)
	};
}
//#endregion
//#region src/skill-bundle.ts
/** Read a bounded skill directory without executing code or resolving references. */
function identity(stat) {
	return [
		stat.dev,
		stat.ino,
		stat.mode,
		stat.size,
		stat.mtimeNs,
		stat.ctimeNs
	].join(":");
}
async function readBundle(directory) {
	const root = await realpath(resolve(directory));
	const observed = /* @__PURE__ */ new Map();
	const files = [];
	let count = 0;
	let total = 0;
	let skillBytes;
	async function visit(path, name, depth) {
		if (++count > 1024 || depth > 12) throw new Error("Bundle exceeds 1024 entries or 12 path levels.");
		if (name && !validBundlePath(name)) throw new Error("Bundle contains an unsupported relative path.");
		const stat = await lstat(path, { bigint: true });
		if (stat.isSymbolicLink()) throw new Error(`Bundle links are not supported: ${JSON.stringify(name)}`);
		observed.set(path, identity(stat));
		if (stat.isDirectory()) {
			const directoryHandle = await opendir(path);
			for await (const entry of directoryHandle) {
				const child = entry.name;
				await visit(join(path, child), name ? `${name}/${child}` : child, depth + 1);
			}
			return;
		}
		if (!stat.isFile()) throw new Error(`Bundle requires regular files: ${JSON.stringify(name)}`);
		if (files.length >= 512) throw new Error("A bundle must not exceed 512 files.");
		const limit = Math.min(name === "SKILL.md" ? MAX_SKILL_BYTES : MAX_BUNDLE_FILE_BYTES, MAX_BUNDLE_BYTES - total);
		if (stat.size > BigInt(limit)) throw new Error("Bundle exceeds its 128 KiB SKILL.md, 16 MiB file or 32 MiB total limit.");
		const handle = await open(path, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0) | (constants.O_NONBLOCK ?? 0));
		try {
			const opened = await handle.stat({ bigint: true });
			if (!opened.isFile() || identity(opened) !== identity(stat)) throw new Error("Bundle changed during inspection; retry a stable directory.");
			const hash = createHash("sha256");
			const buffer = Buffer.alloc(Math.min(limit + 1, 65536));
			const chunks = [];
			let size = 0;
			while (true) {
				const { bytesRead } = await handle.read(buffer, 0, Math.min(buffer.length, limit - size + 1), null);
				if (!bytesRead) break;
				size += bytesRead;
				if (size > limit) throw new Error("Bundle grew beyond its byte limit during inspection.");
				hash.update(buffer.subarray(0, bytesRead));
				if (name === "SKILL.md") chunks.push(Buffer.from(buffer.subarray(0, bytesRead)));
			}
			if (BigInt(size) !== stat.size || identity(await handle.stat({ bigint: true })) !== identity(stat)) throw new Error("Bundle changed during inspection; retry a stable directory.");
			if (name === "SKILL.md") skillBytes = Buffer.concat(chunks);
			total += size;
			files.push({
				path: name,
				bytes: size,
				sha256: hash.digest("hex")
			});
		} finally {
			await handle.close();
		}
	}
	if (!(await lstat(root)).isDirectory()) throw new Error("Choose a skill directory containing SKILL.md.");
	await visit(root, "", 0);
	for (const [path, stamp] of observed) if (identity(await lstat(path, { bigint: true })) !== stamp) throw new Error("Bundle changed during inspection; retry a stable directory.");
	if (skillBytes === void 0) throw new Error("A bundle must contain SKILL.md.");
	new TextDecoder("utf-8", { fatal: true }).decode(skillBytes);
	return {
		manifest: await makeManifest(files.toSorted((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0)),
		skillBytes
	};
}
//#endregion
export { validateManifest as i, MAX_MANIFEST_BYTES as n, compareManifests as r, readBundle as t };
