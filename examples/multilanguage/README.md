# Mixed-language suite

This configuration runs the Python durable service, independent JavaScript
durable service, and JavaScript simulated-ticket policy. All jobs require full
resolution. They retain separate task scores, commands, and image identities.

The [recorded Docker run](run/index.html) resolved all three jobs across 34
case executions using an installed wheel outside the development checkout.
Inspect its [suite JSON](run/suite.json), [JUnit](run/junit.xml), and linked
attempt reports. Absolute candidate paths in the evidence identify that original
execution; generate fresh workspaces when reproducing it.

Follow the [multilanguage guide](../../docs/languages.md) to generate the three
workspaces, pull the images, preview the plan, and run the suite. Candidate paths
resolve relative to this TOML file. Each job starts fresh process/state instances.

The [JavaScript audits](../javascript-audits/README.md) separately check the
declared faults. References are scripted controls, not model evaluations.
