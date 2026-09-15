# Reviewing and sharing recorded evidence

Use the section navigation to move between acceptance gates, repeated attempts,
revision comparisons and the case explorer. These views replay saved reports;
they do not start candidates.

In the case explorer, choose a task and implementation, open a recorded case,
and step through its action and state changes. **Copy evidence link** includes
the task, control, case, seed and zero-based trace-step index. The visible step
label starts at one. Coding cases have no tool trace and use step zero.

The recipient opens the same observation, with focus on its case heading.
**Back to cases** returns focus to the selected row. The URL contains only
selection values, not uploaded evidence or a signed claim about its producer.
Unsupported or out-of-range links display a recovery message. Existing section
anchors continue to navigate without resetting the current case.

Requests time out after 15 seconds. Retry only the failed section, or open its
standalone report. When one audit task pack loads, it stays usable even if the
other fails. Retrying a missing pack can restore a pending shared link.

The browser checks exercise desktop and mobile layouts, clipboard denial,
reload/history restoration, keyboard focus, partial loading and retries.
They do not constitute a full accessibility certification or a browser support
matrix. The original casebook and audit bytes retain their recorded provenance.

## Evidence identity in shared links

Version 2 links include SHA-256 of the exact audit response bytes, together with the task, control, case, seed and trace step. The explorer hashes the fetched audit itself rather than trusting a potentially stale site manifest. If it differs, the linked view is not restored; choose a current case or open the saved original audit. Version 1 links show an explicit legacy notice because they cannot identify the original audit. Duplicate parameters and unsupported versions are rejected.

This is content identity, not an author signature or a substitute for offline evidence verification. HTTPS (or localhost) provides browser hashing. If it is unavailable, reports and downloads remain accessible while evidence-bound sharing is disabled.
