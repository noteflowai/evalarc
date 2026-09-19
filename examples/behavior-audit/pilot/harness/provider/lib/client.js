window.__ModuleLoader__.load({
	id: "dsh-skills-anywhere",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
		let react = require("react");
		let react_jsx_runtime = require("react/jsx-runtime");
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
		//#region src/client/locale.ts
		/** Dictionaries for the settings card. Keys are shared by both languages. */
		const LOCALE_NS = "skills-anywhere";
		const en = {
			title: "Skills Anywhere",
			description: "Skills from other agents, Claude Code plugins and git sources: what the model sees and what stays one search away.",
			expand: "Expand",
			collapse: "Collapse",
			readOnly: "This browser cannot change settings on this host; values are shown read-only.",
			loading: "Reading the skill catalog…",
			loadFailed: "Could not read the skill catalog",
			retry: "Retry",
			refresh: "Refresh",
			summary: "{listed} of {total} skills listed for the model",
			incomplete: "Some directories could not be read; the list may be incomplete.",
			limitLabel: "Catalog budget",
			limitHint: "Maximum skills listed for the model. 0 lists every skill.",
			unlimited: "unlimited",
			search: "Filter by name, description or origin",
			noMatches: "No skills match.",
			stateVisible: "listed",
			stateHidden: "not listed",
			stateDisabled: "author disabled",
			pinned: "pinned",
			renamedFrom: "renamed from {name}",
			pin: "Pin",
			unpin: "Unpin",
			pinHint: "Always list this skill for the model",
			hide: "Hide",
			unhide: "Show",
			hideHint: "Keep this skill out of the model catalog; /name and find_skills still work",
			exclude: "Exclude",
			excludeHint: "Drop this skill from the provider entirely",
			excluded: "Excluded skills",
			restore: "Restore",
			droppedSummary: "{count} duplicates collapsed",
			invalidSummary: "{count} files skipped",
			saving: "Saving…",
			saveFailed: "The change was refused; reload and try again.",
			roots: "Scanned directories",
			rootsSummary: "{present} of {total} directories exist"
		};
		const zh = {
			title: "Skills Anywhere",
			description: "来自其他 agent、Claude Code 插件和 git 源的技能：哪些进入模型目录，哪些留在搜索之外。",
			expand: "展开",
			collapse: "收起",
			readOnly: "当前浏览器无法修改这台主机的设置，以下内容只读。",
			loading: "正在读取技能目录…",
			loadFailed: "无法读取技能目录",
			retry: "重试",
			refresh: "刷新",
			summary: "{total} 个技能中有 {listed} 个列入模型目录",
			incomplete: "部分目录无法读取，列表可能不完整。",
			limitLabel: "目录预算",
			limitHint: "列给模型的最大技能数。0 表示全部列出。",
			unlimited: "不限",
			search: "按名称、描述或来源筛选",
			noMatches: "没有匹配的技能。",
			stateVisible: "已列出",
			stateHidden: "未列出",
			stateDisabled: "作者禁用",
			pinned: "已置顶",
			renamedFrom: "原名 {name}",
			pin: "置顶",
			unpin: "取消置顶",
			pinHint: "始终把这个技能列给模型",
			hide: "隐藏",
			unhide: "显示",
			hideHint: "不进入模型目录；/名称 和 find_skills 仍然可用",
			exclude: "排除",
			excludeHint: "从本 provider 中彻底去掉这个技能",
			excluded: "已排除的技能",
			restore: "恢复",
			droppedSummary: "合并了 {count} 个重复项",
			invalidSummary: "跳过了 {count} 个文件",
			saving: "保存中…",
			saveFailed: "修改被拒绝，请刷新后重试。",
			roots: "扫描的目录",
			rootsSummary: "{total} 个目录中有 {present} 个存在"
		};
		/** `{name}`-style interpolation for the few messages that carry numbers or names. */
		function fill(template, values) {
			return template.replace(/\{(\w+)\}/g, (_match, key) => String(values[key] ?? `{${key}}`));
		}
		//#endregion
		//#region src/client/styles.ts
		const label = "var(--dsw-alias-label-primary)";
		const secondary = "var(--dsw-alias-label-secondary)";
		const tertiary = "var(--dsw-alias-label-tertiary)";
		const border = "var(--dsw-alias-border-l2)";
		const brand = "var(--dsw-alias-brand-primary)";
		const styles = {
			card: {
				listStyle: "none",
				border: `1px solid ${border}`,
				borderRadius: 10,
				marginBottom: 8,
				background: "var(--dsw-alias-bg-layer-3)",
				color: label
			},
			header: {
				display: "flex",
				alignItems: "center",
				gap: 12,
				width: "100%",
				padding: "12px 14px",
				background: "none",
				border: "none",
				color: "inherit",
				cursor: "pointer",
				textAlign: "left",
				font: "inherit"
			},
			headText: {
				display: "flex",
				flexDirection: "column",
				gap: 2,
				flex: 1,
				minWidth: 0
			},
			name: {
				fontWeight: 600,
				fontSize: 14
			},
			description: {
				color: tertiary,
				fontSize: 12,
				lineHeight: 1.4
			},
			chevron: {
				color: tertiary,
				fontSize: 12,
				transition: "transform .15s"
			},
			body: {
				padding: "0 14px 14px",
				display: "flex",
				flexDirection: "column",
				gap: 12
			},
			status: {
				color: tertiary,
				fontSize: 12,
				margin: 0
			},
			errorText: {
				color: "var(--dsw-alias-label-error)",
				fontSize: 12,
				margin: 0
			},
			row: {
				display: "flex",
				alignItems: "center",
				gap: 8,
				flexWrap: "wrap"
			},
			input: {
				font: "inherit",
				fontSize: 13,
				color: label,
				background: "transparent",
				border: `1px solid ${border}`,
				borderRadius: 6,
				padding: "5px 8px",
				minWidth: 0
			},
			search: {
				flex: 1,
				minWidth: 180
			},
			limitInput: {
				width: 72,
				textAlign: "right"
			},
			hint: {
				color: tertiary,
				fontSize: 12
			},
			group: {
				margin: 0,
				padding: 0,
				listStyle: "none",
				display: "flex",
				flexDirection: "column",
				gap: 4
			},
			groupTitle: {
				color: secondary,
				fontSize: 12,
				fontWeight: 600,
				margin: "8px 0 4px",
				textTransform: "uppercase",
				letterSpacing: ".04em"
			},
			skill: {
				display: "grid",
				gridTemplateColumns: "minmax(0, 1fr) auto",
				gap: "2px 12px",
				alignItems: "center",
				padding: "6px 8px",
				borderRadius: 6,
				border: `1px solid transparent`
			},
			skillHidden: { opacity: .7 },
			skillName: {
				fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
				fontSize: 13,
				display: "flex",
				gap: 6,
				alignItems: "center",
				flexWrap: "wrap"
			},
			skillMeta: {
				gridColumn: "1 / 2",
				color: tertiary,
				fontSize: 12,
				overflow: "hidden",
				textOverflow: "ellipsis",
				whiteSpace: "nowrap"
			},
			actions: {
				gridColumn: "2 / 3",
				gridRow: "1 / 3",
				display: "flex",
				gap: 6
			},
			tag: {
				fontSize: 11,
				lineHeight: "16px",
				padding: "0 6px",
				borderRadius: 999,
				border: `1px solid ${border}`,
				color: secondary,
				whiteSpace: "nowrap"
			},
			tagOn: {
				borderColor: brand,
				color: brand
			},
			tagOff: { color: tertiary },
			button: {
				font: "inherit",
				fontSize: 12,
				color: label,
				background: "transparent",
				border: `1px solid ${border}`,
				borderRadius: 6,
				padding: "3px 8px",
				cursor: "pointer"
			},
			buttonActive: {
				borderColor: brand,
				color: brand
			},
			buttonDisabled: {
				opacity: .5,
				cursor: "default"
			},
			details: {
				color: tertiary,
				fontSize: 12
			},
			mono: { fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }
		};
		//#endregion
		//#region src/client/index.tsx
		/**
		* dsh-skills-anywhere — browser half.
		*
		* Registers one card into the web Settings → Plugins → *Plugin configuration*
		* tab (`settings.plugin.item`, keyed by the `skills-anywhere` settings
		* namespace). The card lists every skill the provider found, grouped by where
		* it lives, shows whether the model catalog lists it, and lets the user pin,
		* hide or exclude skills. Edits write through the dsh settings scope, so they
		* persist in the profile's settings document and take effect immediately: the
		* host provider re-applies the namespace on every commit.
		*
		* Runtime services (Cordis `inject`): `slots`, `locale`, `settingsScope`. The
		* report is fetched from the host's exact `/api` route with the page's own
		* credentials. Bundled as a lazy-CJS factory for the dsh client module system.
		*
		* @module dsh-skills-anywhere/client
		*/
		/** Client services the bundle needs before `apply` runs. */
		const inject = [
			"slots",
			"locale",
			"settingsScope"
		];
		/** Register the dictionaries and the settings card. */
		function apply(ctx) {
			ctx.effect(() => ctx.locale.register(LOCALE_NS, {
				en,
				zh
			}), "skills-anywhere: dictionaries");
			const face = {
				scope: ctx.settingsScope.bind({ namespace: SETTINGS_NAMESPACE }),
				fetchReport: async (signal) => {
					const response = await fetch(new URL(REPORT_PATH, location.href), {
						method: "POST",
						headers: { "content-type": "application/json" },
						body: "{}",
						credentials: "same-origin",
						signal
					});
					if (!response.ok) throw new Error(`HTTP ${response.status}`);
					const result = await response.json();
					if (!result.ok) throw new Error(`${result.error.code}: ${result.error.message}`);
					return result.value;
				}
			};
			ctx.slots.inject("settings.plugin.item", () => ctx.slots.register({
				name: "settings.plugin.item",
				key: SETTINGS_NAMESPACE,
				locale: LOCALE_NS,
				inject: () => ({ ...face })
			}, SkillsAnywhereCard));
		}
		/** Settings card for the skills-anywhere provider. Exported for tests. */
		function SkillsAnywhereCard(props) {
			const { t, scope, fetchReport } = props;
			const subscribe = (0, react.useCallback)((listener) => scope.subscribe(listener), [scope]);
			const getSnapshot = (0, react.useCallback)(() => scope.getSnapshot(), [scope]);
			const snapshot = (0, react.useSyncExternalStore)(subscribe, getSnapshot, getSnapshot);
			const [open, setOpen] = (0, react.useState)(false);
			const [report, setReport] = (0, react.useState)({ kind: "loading" });
			const [reloadTick, setReloadTick] = (0, react.useState)(0);
			const [saving, setSaving] = (0, react.useState)(false);
			const [saveError, setSaveError] = (0, react.useState)(void 0);
			const [query, setQuery] = (0, react.useState)("");
			(0, react.useEffect)(() => {
				if (!open) return;
				const abort = new AbortController();
				setReport((current) => current.kind === "ready" ? current : { kind: "loading" });
				fetchReport(abort.signal).then((value) => {
					if (!abort.signal.aborted) setReport({
						kind: "ready",
						report: value
					});
				}).catch((error) => {
					if (!abort.signal.aborted) setReport({
						kind: "failed",
						message: error instanceof Error ? error.message : String(error)
					});
				});
				return () => abort.abort();
			}, [
				open,
				fetchReport,
				snapshot.revision,
				reloadTick
			]);
			const settings = snapshot.value;
			const writable = snapshot.writable && !saving;
			const write = (0, react.useCallback)(async (next) => {
				setSaving(true);
				setSaveError(void 0);
				const ops = [];
				if (next.catalog !== void 0) for (const [key, value] of Object.entries(next.catalog)) ops.push({
					op: "set",
					path: ["catalog", key],
					value
				});
				if (next.excludeSkills !== void 0) ops.push({
					op: "set",
					path: ["excludeSkills"],
					value: next.excludeSkills
				});
				try {
					await scope.mutate(ops);
					setReloadTick((tick) => tick + 1);
				} catch (error) {
					setSaveError(error instanceof Error ? error.message : String(error));
				} finally {
					setSaving(false);
				}
			}, [scope]);
			const toggleList = (0, react.useCallback)((list, name) => {
				if (settings === void 0) return;
				const current = new Set(settings.catalog[list]);
				if (current.has(name)) current.delete(name);
				else current.add(name);
				const pin = new Set(list === "pin" ? current : settings.catalog.pin);
				const hide = new Set(list === "hide" ? current : settings.catalog.hide);
				if (list === "pin" && current.has(name)) hide.delete(name);
				if (list === "hide" && current.has(name)) pin.delete(name);
				write({ catalog: {
					limit: settings.catalog.limit,
					pin: [...pin].toSorted(),
					hide: [...hide].toSorted()
				} });
			}, [settings, write]);
			const setExcluded = (0, react.useCallback)((name, excluded) => {
				if (settings === void 0) return;
				const current = new Set(settings.excludeSkills);
				if (excluded) current.add(name);
				else current.delete(name);
				write({ excludeSkills: [...current].toSorted() });
			}, [settings, write]);
			const setLimit = (0, react.useCallback)((text) => {
				if (settings === void 0) return;
				const limit = text.trim() === "" ? 0 : Number(text);
				if (!Number.isInteger(limit) || limit < 0 || limit === settings.catalog.limit) return;
				write({ catalog: {
					...settings.catalog,
					limit
				} });
			}, [settings, write]);
			const groups = (0, react.useMemo)(() => {
				if (report.kind !== "ready") return [];
				const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
				const matches = (skill) => terms.every((term) => skill.name.toLowerCase().includes(term) || skill.description.toLowerCase().includes(term) || skill.origin.toLowerCase().includes(term));
				const byGroup = /* @__PURE__ */ new Map();
				for (const skill of report.report.skills) {
					if (!matches(skill)) continue;
					const list = byGroup.get(skill.group);
					if (list === void 0) byGroup.set(skill.group, [skill]);
					else list.push(skill);
				}
				return [...byGroup.entries()];
			}, [report, query]);
			if (snapshot.status !== "ready" || settings === void 0) return null;
			const title = t("title");
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("li", {
				style: styles.card,
				children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
					type: "button",
					style: styles.header,
					"aria-expanded": open,
					"aria-label": `${t(open ? "collapse" : "expand")}: ${title}`,
					onClick: () => setOpen(!open),
					children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
						style: styles.headText,
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							style: styles.name,
							children: title
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							style: styles.description,
							children: t("description")
						})]
					}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
						style: {
							...styles.chevron,
							transform: open ? "rotate(180deg)" : void 0
						},
						"aria-hidden": "true",
						children: "▾"
					})]
				}), open ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
					style: styles.body,
					children: [
						!snapshot.writable ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
							style: styles.status,
							role: "status",
							children: t("readOnly")
						}) : null,
						/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
							style: styles.row,
							children: [
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("label", {
									style: styles.hint,
									htmlFor: "skills-anywhere-limit",
									children: t("limitLabel")
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("input", {
									id: "skills-anywhere-limit",
									style: {
										...styles.input,
										...styles.limitInput
									},
									type: "number",
									min: 0,
									step: 1,
									defaultValue: settings.catalog.limit,
									disabled: !writable,
									onBlur: (event) => setLimit(event.currentTarget.value),
									onKeyDown: (event) => {
										if (event.key === "Enter") setLimit(event.currentTarget.value);
									},
									"aria-describedby": "skills-anywhere-limit-hint"
								}, `limit-${settings.catalog.limit}`),
								/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
									id: "skills-anywhere-limit-hint",
									style: styles.hint,
									children: [
										settings.catalog.limit === 0 ? t("unlimited") : "",
										" ",
										t("limitHint")
									]
								})
							]
						}),
						report.kind === "loading" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
							style: styles.status,
							role: "status",
							children: t("loading")
						}) : null,
						report.kind === "failed" ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", {
							style: styles.errorText,
							role: "alert",
							children: [
								t("loadFailed"),
								": ",
								report.message,
								" ",
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
									type: "button",
									style: styles.button,
									onClick: () => setReloadTick((tick) => tick + 1),
									children: t("retry")
								})
							]
						}) : null,
						report.kind === "ready" ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [
							/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
								style: styles.row,
								children: [
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
										style: styles.hint,
										children: fill(t("summary"), {
											listed: report.report.listed,
											total: report.report.skills.length
										})
									}),
									!report.report.complete ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
										style: styles.errorText,
										children: t("incomplete")
									}) : null,
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { style: { flex: 1 } }),
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
										type: "button",
										style: styles.button,
										onClick: () => setReloadTick((tick) => tick + 1),
										children: t("refresh")
									})
								]
							}),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("input", {
								style: {
									...styles.input,
									...styles.search
								},
								type: "search",
								placeholder: t("search"),
								value: query,
								onChange: (event) => setQuery(event.currentTarget.value),
								"aria-label": t("search")
							}),
							saving ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
								style: styles.status,
								role: "status",
								children: t("saving")
							}) : null,
							saveError !== void 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", {
								style: styles.errorText,
								role: "alert",
								children: [
									t("saveFailed"),
									" (",
									saveError,
									")"
								]
							}) : null,
							groups.length === 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
								style: styles.status,
								children: t("noMatches")
							}) : null,
							groups.map(([group, skills]) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h4", {
								style: styles.groupTitle,
								children: group
							}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("ul", {
								style: styles.group,
								children: skills.map((skill) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)(SkillRow, {
									skill,
									t,
									writable,
									onPin: () => toggleList("pin", skill.name),
									onHide: () => toggleList("hide", skill.name),
									onExclude: () => setExcluded(skill.name, true)
								}, skill.name))
							})] }, group)),
							settings.excludeSkills.length > 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h4", {
								style: styles.groupTitle,
								children: t("excluded")
							}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("ul", {
								style: styles.group,
								children: settings.excludeSkills.map((name) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("li", {
									style: styles.skill,
									children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
										style: styles.skillName,
										children: name
									}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
										style: styles.actions,
										children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
											type: "button",
											style: {
												...styles.button,
												...writable ? {} : styles.buttonDisabled
											},
											disabled: !writable,
											onClick: () => setExcluded(name, false),
											children: t("restore")
										})
									})]
								}, name))
							})] }) : null,
							/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("details", {
								style: styles.details,
								children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("summary", { children: [
									fill(t("rootsSummary"), {
										present: report.report.roots.filter((root) => root.exists).length,
										total: report.report.roots.length
									}),
									report.report.dropped.length > 0 ? ` · ${fill(t("droppedSummary"), { count: report.report.dropped.length })}` : "",
									report.report.invalid.length > 0 ? ` · ${fill(t("invalidSummary"), { count: report.report.invalid.length })}` : ""
								] }), /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("ul", {
									style: styles.group,
									children: [report.report.roots.filter((root) => root.exists).map((root) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("li", {
										style: styles.mono,
										children: [
											root.label,
											" — ",
											root.path,
											" (",
											root.count,
											")"
										]
									}, root.path)), report.report.invalid.map((entry) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("li", {
										style: styles.mono,
										children: [
											entry.path,
											": ",
											entry.reason
										]
									}, entry.path))]
								})]
							})
						] }) : null
					]
				}) : null]
			});
		}
		function SkillRow({ skill, t, writable, onPin, onHide, onExclude }) {
			const stateKey = skill.state === "visible" ? "stateVisible" : skill.state === "hidden" ? "stateHidden" : "stateDisabled";
			const stateStyle = skill.state === "visible" ? styles.tagOn : styles.tagOff;
			const disabledButton = writable && !skill.authorDisabled ? {} : styles.buttonDisabled;
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("li", {
				style: {
					...styles.skill,
					...skill.state === "visible" ? {} : styles.skillHidden
				},
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
						style: styles.skillName,
						children: [
							skill.name,
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								style: {
									...styles.tag,
									...stateStyle
								},
								children: t(stateKey)
							}),
							skill.pinned ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								style: {
									...styles.tag,
									...styles.tagOn
								},
								children: t("pinned")
							}) : null,
							skill.renamedFrom !== void 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								style: styles.tag,
								children: fill(t("renamedFrom"), { name: skill.renamedFrom })
							}) : null
						]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
						style: styles.skillMeta,
						title: `${skill.path}\n${skill.description}`,
						children: [
							skill.origin,
							" · ",
							skill.description
						]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("span", {
						style: styles.actions,
						children: [
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
								type: "button",
								style: {
									...styles.button,
									...skill.pinned ? styles.buttonActive : {},
									...disabledButton
								},
								disabled: !writable || skill.authorDisabled,
								title: t("pinHint"),
								onClick: onPin,
								children: t(skill.pinned ? "unpin" : "pin")
							}),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
								type: "button",
								style: {
									...styles.button,
									...skill.hidden ? styles.buttonActive : {},
									...disabledButton
								},
								disabled: !writable || skill.authorDisabled,
								title: t("hideHint"),
								onClick: onHide,
								children: t(skill.hidden ? "unhide" : "hide")
							}),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
								type: "button",
								style: {
									...styles.button,
									...writable ? {} : styles.buttonDisabled
								},
								disabled: !writable,
								title: t("excludeHint"),
								onClick: onExclude,
								children: t("exclude")
							})
						]
					})
				]
			});
		}
		//#endregion
		exports.SkillsAnywhereCard = SkillsAnywhereCard;
		exports.apply = apply;
		exports.inject = inject;
		return module.exports;
	}
});
