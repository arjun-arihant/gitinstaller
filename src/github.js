import AdmZip from "adm-zip";
import { mkdirSync, writeFileSync } from "fs";
import { join, dirname } from "path";

export async function downloadRepo(repoUrl, destDir) {
  const parsed = parseRepoUrl(repoUrl);
  if (!parsed) {
    throw new Error(`Cannot parse GitHub URL: ${repoUrl}`);
  }

  const { owner, repo } = parsed;
  const branch = await detectBranch(owner, repo);

  const zipUrl = `https://github.com/${owner}/${repo}/archive/refs/heads/${branch}.zip`;
  const response = await fetch(zipUrl);

  if (!response.ok) {
    throw new Error(
      `Failed to download repo: HTTP ${response.status} from ${zipUrl}`
    );
  }

  const buffer = Buffer.from(await response.arrayBuffer());
  const zip = new AdmZip(buffer);
  const entries = zip.getEntries();

  // GitHub ZIPs wrap everything in {repo}-{branch}/ — strip that prefix
  const prefix = `${repo}-${branch}/`;

  for (const entry of entries) {
    const entryName = entry.entryName;
    if (!entryName.startsWith(prefix)) continue;

    const relativePath = entryName.slice(prefix.length);
    if (!relativePath) continue; // skip the root folder entry itself

    const targetPath = join(destDir, relativePath);

    if (entry.isDirectory) {
      mkdirSync(targetPath, { recursive: true });
    } else {
      mkdirSync(dirname(targetPath), { recursive: true });
      writeFileSync(targetPath, entry.getData());
    }
  }

  return { owner, repo, branch };
}

function parseRepoUrl(url) {
  const match = url.match(
    /github\.com\/([a-zA-Z0-9._-]+)\/([a-zA-Z0-9._-]+)/
  );
  if (!match) return null;
  return { owner: match[1], repo: match[2].replace(/\.git$/, "") };
}

async function detectBranch(owner, repo) {
  // Try main first
  for (const branch of ["main", "master"]) {
    const url = `https://github.com/${owner}/${repo}/archive/refs/heads/${branch}.zip`;
    const resp = await fetch(url, { method: "HEAD" });
    if (resp.ok) return branch;
  }

  // Fall back to GitHub API for default branch
  const apiResp = await fetch(
    `https://api.github.com/repos/${owner}/${repo}`,
    {
      headers: { Accept: "application/vnd.github.v3+json" },
    }
  );
  if (!apiResp.ok) {
    throw new Error(`Cannot determine default branch for ${owner}/${repo}`);
  }
  const data = await apiResp.json();
  return data.default_branch;
}
