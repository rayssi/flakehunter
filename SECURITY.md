# Security policy

## Supported versions

Security fixes are released for the latest version of FlakeHunter only.
Please upgrade to the latest release before reporting a problem.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Report it privately instead, from the
[Security tab of the repository](https://github.com/rayssi/flakehunter/security/advisories/new)
("Report a vulnerability"). Please include:

- the FlakeHunter version (`flakehunter --version`);
- what an attacker could do, and how;
- the smallest input that shows the problem, if possible (an archive or a `*-result.json` file).

You will get an answer within 7 days. Once the problem is confirmed, a fix is released as soon as
possible and the vulnerability is published as a GitHub security advisory, with credit to you
if you wish.

## What FlakeHunter does with your data

- It only reads the history folder you give it and only writes to its own output folder.
- Archives are read in memory and never extracted to disk.
- It makes no network connection and has no runtime dependencies.
- Test names and error messages are escaped in the HTML report.

A report showing that FlakeHunter breaks one of these promises is a security issue.
