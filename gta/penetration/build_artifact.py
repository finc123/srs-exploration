"""Fill template.html with gta6_penetration.json -> gta_6_penetration_analyses.html (run from gta/penetration)."""
import json

data = open("gta6_penetration.json").read()
html = (open("template.html", encoding="utf-8").read()
        .replace("__DATA__", data)
        .replace("__LAST__", json.loads(data)["games"]["GTA6"]["last_date"]))
open("gta_6_penetration_analyses.html", "w", encoding="utf-8").write(html)
