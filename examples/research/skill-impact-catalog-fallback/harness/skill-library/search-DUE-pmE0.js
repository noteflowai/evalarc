//#region src/search.ts
/** Split a query into lowercase alphanumeric terms. */
function queryTerms(query) {
	return [...new Set(query.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter((term) => term.length > 1))];
}
/**
* Rank skills against a keyword query. Name matches weigh most, then
* description, `whenToUse`, and origin labels. Skills matching no term are
* dropped; ties break alphabetically.
*/
function searchSkills(skills, query, limit) {
	const terms = queryTerms(query);
	if (terms.length === 0) return [];
	const matches = [];
	for (const skill of skills) {
		const nameText = skill.name.toLowerCase();
		const nameWords = nameText.split("-");
		const description = skill.description.toLowerCase();
		const whenToUse = (skill.whenToUse ?? "").toLowerCase();
		const origin = `${skill.source} ${skill.provider}`.toLowerCase();
		let score = 0;
		let matched = 0;
		for (const term of terms) {
			let termScore = 0;
			if (nameText === term) termScore += 60;
			else if (nameWords.includes(term)) termScore += 40;
			else if (nameText.includes(term)) termScore += 20;
			if (description.includes(term)) termScore += 8;
			if (whenToUse.includes(term)) termScore += 6;
			if (origin.includes(term)) termScore += 2;
			if (termScore > 0) matched += 1;
			score += termScore;
		}
		if (matched === 0) continue;
		score += matched * 30;
		matches.push({
			name: skill.name,
			description: skill.description,
			source: skill.source,
			provider: skill.provider,
			listed: skill.invocation.modelInvocable,
			score
		});
	}
	return matches.toSorted((left, right) => right.score - left.score || left.name.localeCompare(right.name)).slice(0, limit);
}
//#endregion
export { searchSkills as n, queryTerms as t };
