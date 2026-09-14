import { _ as Config, a as resolveSource, b as resolveConfig, c as writeSourcesFile, d as originLabel, f as discover, h as agentById, i as readSourcesFile, l as applyCatalogBudget, m as AGENTS, n as hasGit, o as sameRepository, p as findProjectRoot, r as readLock, s as syncSource, t as SkillsAnywhereProvider, u as originGroup, v as DEFAULT_RANKS, y as projectSourcesFile } from "./provider-D_asoyBt.js";
import { a as parseSkillMarkdown, i as normalizeSkillName, o as splitFrontmatter, r as isSkillName } from "./skill-check-Da47aHh6.js";
import z from "@deepseek-ai/schemastery";
//#region src/web-protocol.ts
/** Settings namespace the host registers and the card edits. */
const SETTINGS_NAMESPACE = "skills-anywhere";
/**
* Exact Fetch route the host registers on the dsh connection's shared `/api`
* channel (the public seam for feature packages; it inherits the browser-trust
* fence and authentication) and the card POSTs to. Body: `ReportRequest` JSON;
* response: `RpcResult<ReportView>` JSON.
*/
const REPORT_PATH = "/api/skills-anywhere/report";
//#endregion
//#region src/web.ts
/** Schema of the `skills-anywhere` settings namespace: the runtime-editable part of the plugin config. */
const SettingsSchema = z.object({
	catalog: z.object({
		limit: z.number().min(0).step(1).default(50),
		pin: z.array(z.string()).default([]),
		hide: z.array(z.string()).default([])
	}).default({
		limit: 50,
		pin: [],
		hide: []
	}),
	excludeSkills: z.array(z.string()).default([])
});
/** The composition entry for the settings namespace, derived from the resolved plugin config. */
function settingsEntry(config) {
	return {
		catalog: {
			limit: config.catalog.limit,
			pin: [...config.catalog.pin],
			hide: [...config.catalog.hide]
		},
		excludeSkills: [...config.excludeSkills]
	};
}
/** Serve one report request. Exported for tests and custom transports. */
async function handleReport(provider, payload) {
	if (provider === void 0) return {
		ok: false,
		error: {
			code: "skills-anywhere/not-ready",
			message: "the skills-anywhere provider is not registered yet",
			details: {}
		}
	};
	const request = typeof payload === "object" && payload !== null ? payload : {};
	const cwd = typeof request.cwd === "string" && request.cwd.length > 0 ? request.cwd : void 0;
	try {
		return {
			ok: true,
			value: await provider.snapshot(cwd)
		};
	} catch (error) {
		return {
			ok: false,
			error: {
				code: "skills-anywhere/internal",
				message: error instanceof Error ? error.message : String(error),
				details: {}
			}
		};
	}
}
/**
* Attach the settings namespace and the report endpoint to `ctx`. `provider`
* is a getter because dsh constructs the provider lazily through
* `ctx.skills.registerProvider`.
*/
function installWeb(ctx, provider, config, log) {
	const entry = settingsEntry(config);
	let current = () => entry;
	ctx.inject(["settings"], (settingsCtx) => {
		settingsCtx.settings.installSection(ctx, SETTINGS_NAMESPACE, SettingsSchema, entry, {
			setSource: (source) => {
				current = source;
			},
			onChange: () => {
				const next = current();
				provider()?.reconfigure(next);
			}
		});
		log.info(`skills-anywhere: settings namespace "${SETTINGS_NAMESPACE}" registered`);
	});
	ctx.inject(["connection"], (connectionCtx) => {
		const connection = connectionCtx.connection;
		connectionCtx.effect(() => {
			const dispose = connection.fetch.register({
				path: REPORT_PATH,
				methods: ["POST"],
				requestBody: "buffered",
				fetch: async (request) => {
					const payload = await request.json().catch(() => ({}));
					const result = await handleReport(provider(), payload);
					return new Response(JSON.stringify(result), {
						status: 200,
						headers: { "content-type": "application/json" }
					});
				}
			});
			return () => {
				dispose();
			};
		}, "skills-anywhere: report route");
		log.info(`skills-anywhere: web route "POST ${REPORT_PATH}" registered`);
	});
	currentSettings.set(ctx, () => current());
}
const currentSettings = /* @__PURE__ */ new WeakMap();
/** Settings currently in force for `ctx` (composition entry until the settings service attaches). */
function settingsInForce(ctx) {
	return currentSettings.get(ctx)?.();
}
//#endregion
//#region src/index.ts
/** Cordis plugin name; stable across releases. */
const name = "skills-anywhere";
/** The skill registry must exist before the provider can register. */
const inject = ["skills"];
/**
* Register the skills-anywhere provider on `ctx.skills`, plus the runtime
* settings namespace and the web report endpoint when their services exist.
*/
function apply(ctx, config = {}) {
	const resolved = resolveConfig(config);
	let provider;
	const log = {
		info: (message) => ctx.logger.info(message),
		warn: (message) => ctx.logger.warn(message),
		debug: (message) => ctx.logger.debug(message)
	};
	installWeb(ctx, () => provider, resolved, log);
	ctx.skills.registerProvider((control) => {
		provider = new SkillsAnywhereProvider(resolved, log, control);
		const settings = settingsInForce(ctx);
		if (settings !== void 0) provider.reconfigure(settings);
		return provider;
	});
	ctx.effect(() => () => {
		provider?.dispose();
	}, "skills-anywhere provider");
	ctx.logger.info(`skills-anywhere: provider "${resolved.providerName}" registered (agents=${resolved.agents}, claudePlugins=${resolved.claudePlugins}, sources=${resolved.sources.length}${resolved.sourcesFiles ? "+files" : ""})`);
}
//#endregion
export { AGENTS, Config, DEFAULT_RANKS, REPORT_PATH, SETTINGS_NAMESPACE, SettingsSchema, SkillsAnywhereProvider, agentById, apply, applyCatalogBudget, discover, findProjectRoot, handleReport, hasGit, inject, installWeb, isSkillName, name, normalizeSkillName, originGroup, originLabel, parseSkillMarkdown, projectSourcesFile, readLock, readSourcesFile, resolveConfig, resolveSource, sameRepository, settingsEntry, splitFrontmatter, syncSource, writeSourcesFile };
