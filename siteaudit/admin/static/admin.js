const STAGES = [
  ["new", "Novo"], ["review", "Revisar"], ["qualified", "Qualificado"],
  ["contacted", "Contatado"], ["replied", "Respondeu"], ["won", "Ganho"],
  ["lost", "Perdido"], ["do_not_contact", "Não contatar"],
];
const $ = (selector) => document.querySelector(selector);
const byId = (id) => document.getElementById(id);
let refreshTimer = null;
let selectedRunId = null;

function escapeText(value) {
  return String(value ?? "");
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Erro HTTP ${response.status}`);
  return data;
}

function notify(message, isError = false) {
  const box = byId("notice");
  box.textContent = message;
  box.className = `notice${isError ? " error" : ""}`;
  box.hidden = false;
  window.setTimeout(() => { box.hidden = true; }, 6500);
}

async function loadProviders() {
  const data = await api("/api/providers");
  const container = byId("providers");
  container.replaceChildren();
  data.providers.forEach((provider) => {
    const label = document.createElement("label");
    label.className = "provider-option";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.name = "provider";
    checkbox.value = provider.id;
    checkbox.checked = ["bing", "ddg"].includes(provider.id);
    checkbox.disabled = provider.enabled === false;
    const text = document.createElement("span");
    const title = document.createElement("b");
    title.textContent = provider.label;
    const description = document.createElement("small");
    description.textContent = provider.enabled === false
      ? "Pausado até migração do conector e implantação de limites de custo."
      : provider.description + (provider.needs_key ? " · requer chave configurada" : "");
    text.append(title, description);
    label.append(checkbox, text);
    container.append(label);
  });
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function setSummary(runs, leads) {
  byId("summary-runs").textContent = runs.length;
  byId("summary-leads").textContent = leads.length;
  byId("summary-active").textContent = leads.filter((lead) => ["new", "review", "qualified", "contacted", "replied"].includes(lead.outreach_status)).length;
}

function renderRuns(runs) {
  const body = byId("runs-body");
  body.replaceChildren();
  if (!runs.length) {
    const row = body.insertRow();
    const cell = row.insertCell();
    cell.colSpan = 7;
    cell.className = "empty-cell";
    cell.textContent = "Ainda não há execuções. Configure uma busca acima para começar.";
    return;
  }
  for (const run of runs) {
    const row = body.insertRow();
    const config = run.config || {};
    const locations = (config.locations || []).map((location) => [location.city, location.state].filter(Boolean).join(" / ")).join(", ");
    const cells = [config.business_type || "—", locations || "—", run.progress || "—"];
    for (const value of cells) {
      const cell = row.insertCell();
      cell.textContent = value;
    }
    const status = row.insertCell();
    const badge = document.createElement("span");
    badge.className = `status ${run.status}`;
    badge.textContent = ({ queued: "Na fila", running: "Em andamento", completed: "Concluída", failed: "Falhou", interrupted: "Interrompida" })[run.status] || run.status;
    status.append(badge);
    const count = row.insertCell();
    count.textContent = String(run.leads_found ?? 0);
    const created = row.insertCell();
    created.textContent = formatDate(run.created_at);
    const action = row.insertCell();
    const button = document.createElement("button");
    button.type = "button";
    button.className = "small-button";
    button.textContent = "Ver leads";
    button.addEventListener("click", () => {
      selectedRunId = run.id;
      byId("lead-search").value = "";
      loadLeads();
      byId("leads-title").scrollIntoView({ behavior: "smooth", block: "center" });
    });
    action.append(button);
    if (run.errors?.length) {
      const detail = document.createElement("small");
      detail.textContent = `${run.errors.length} aviso(s) — ${run.errors[0]}`;
      detail.title = run.errors.join("\n");
      row.cells[2].append(document.createElement("br"), detail);
    }
  }
}

function renderLeads(leads) {
  const body = byId("leads-body");
  body.replaceChildren();
  if (!leads.length) {
    const row = body.insertRow();
    const cell = row.insertCell();
    cell.colSpan = 6;
    cell.className = "empty-cell";
    cell.textContent = "Nenhum lead corresponde à busca ou ao filtro.";
    return;
  }
  for (const lead of leads) {
    const row = body.insertRow();
    const company = row.insertCell();
    const name = document.createElement("strong");
    name.textContent = lead.name || "Sem nome";
    company.append(name);
    if (lead.website && /^https?:\/\//i.test(lead.website)) {
      const link = document.createElement("a");
      link.href = lead.website;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = lead.website;
      link.className = "lead-link";
      company.append(link);
    } else {
      const sub = document.createElement("small");
      sub.textContent = lead.maps_url ? "Ficha/localização encontrada" : "Site não localizado nesta busca";
      company.append(sub);
    }

    const location = row.insertCell();
    location.textContent = [lead.city, lead.state].filter(Boolean).join(" / ") || "—";
    const category = document.createElement("small");
    category.textContent = lead.category || "";
    location.append(category);

    const presence = row.insertCell();
    const badge = document.createElement("span");
    badge.className = `status ${lead.site_status === "audit_ok" ? "completed" : lead.site_status === "audit_error" ? "failed" : ""}`;
    badge.textContent = ({ website_found_unverified: "Site encontrado · validar", website_not_located: "Site não localizado", audit_ok: "Site auditado", audit_error: "Auditoria falhou", not_checked: "Não verificado" })[lead.site_status] || lead.site_status;
    presence.append(badge);
    if (lead.audit?.score !== undefined && lead.audit?.score !== null) {
      const score = document.createElement("small");
      score.textContent = `Nota técnica: ${lead.audit.score}/100`;
      presence.append(score);
      const findings = lead.audit.findings || [];
      if (findings.length) {
        const details = document.createElement("details");
        const summary = document.createElement("summary");
        summary.textContent = `${findings.length} achado(s)`;
        details.append(summary);
        const list = document.createElement("ul");
        list.className = "finding-list";
        findings.slice(0, 8).forEach((finding) => {
          const item = document.createElement("li");
          item.textContent = `${finding.severity || ""}: ${finding.title || "Achado"}`;
          list.append(item);
        });
        details.append(list);
        presence.append(details);
      }
    }

    const contact = row.insertCell();
    contact.textContent = lead.phone || "—";
    const source = document.createElement("small");
    source.textContent = lead.source || "";
    contact.append(source);

    const priority = row.insertCell();
    const score = lead.audit?.score;
    priority.textContent = !lead.website ? "Presença própria não localizada" : score == null ? "Aguardando auditoria" : score < 50 ? "Revisar oportunidade" : score < 75 ? "Melhorias possíveis" : "Site estruturado";
    if (lead.error) {
      const error = document.createElement("small");
      error.textContent = lead.error;
      priority.append(error);
    }

    const stageCell = row.insertCell();
    const select = document.createElement("select");
    select.className = "lead-stage";
    for (const [value, label] of STAGES) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      option.selected = lead.outreach_status === value;
      select.append(option);
    }
    select.addEventListener("change", async () => {
      try {
        await api(`/api/leads/${lead.id}`, { method: "PATCH", body: JSON.stringify({ outreach_status: select.value }) });
        notify("Etapa comercial atualizada.");
      } catch (error) { notify(error.message, true); }
    });
    const notes = document.createElement("small");
    notes.textContent = lead.notes ? `Nota: ${lead.notes}` : "Clique duas vezes para adicionar nota";
    notes.title = "Duplo clique para editar nota";
    notes.style.cursor = "pointer";
    notes.addEventListener("dblclick", async () => {
      const value = window.prompt("Notas internas deste lead:", lead.notes || "");
      if (value === null) return;
      try {
        await api(`/api/leads/${lead.id}`, { method: "PATCH", body: JSON.stringify({ notes: value }) });
        notify("Nota salva.");
        await loadLeads();
      } catch (error) { notify(error.message, true); }
    });
    stageCell.append(select, notes);
  }
}

async function loadLeads(runId = selectedRunId) {
  const params = new URLSearchParams();
  const query = byId("lead-search").value.trim();
  const stage = byId("stage-filter").value;
  if (runId) params.set("run_id", runId);
  if (query) params.set("q", query);
  if (stage) params.set("stage", stage);
  const data = await api(`/api/leads?${params}`);
  renderLeads(data.leads);
  return data.leads;
}

async function refreshAll() {
  const [runsData, allLeadsData] = await Promise.all([api("/api/runs"), api("/api/leads")]);
  renderRuns(runsData.runs);
  const displayed = selectedRunId ? await api(`/api/leads?run_id=${encodeURIComponent(selectedRunId)}`) : allLeadsData;
  renderLeads(displayed.leads);
  setSummary(runsData.runs, allLeadsData.leads);
  const busy = runsData.runs.some((run) => ["queued", "running"].includes(run.status));
  if (busy && !refreshTimer) refreshTimer = window.setInterval(() => refreshAll().catch(() => {}), 4000);
  if (!busy && refreshTimer) { window.clearInterval(refreshTimer); refreshTimer = null; }
}

function parseLines(value) { return value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean); }

byId("quantity-mode").addEventListener("change", () => {
  byId("quantity-help").textContent = byId("quantity-mode").value === "total" ? "Total distribuído entre as localidades." : "Quantidade solicitada em cada localidade.";
});
byId("audit-sites").addEventListener("change", () => { byId("audit-limit-wrap").hidden = !byId("audit-sites").checked; });
byId("select-defaults").addEventListener("click", () => {
  document.querySelectorAll('input[name="provider"]').forEach((checkbox) => { checkbox.checked = ["bing", "ddg"].includes(checkbox.value); });
});
byId("refresh").addEventListener("click", () => refreshAll().catch((error) => notify(error.message, true)));
byId("lead-search").addEventListener("input", () => loadLeads().catch((error) => notify(error.message, true)));
byId("stage-filter").addEventListener("change", () => loadLeads().catch((error) => notify(error.message, true)));
for (const [value, label] of STAGES) {
  const option = document.createElement("option"); option.value = value; option.textContent = label; byId("stage-filter").append(option);
}

byId("search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = byId("submit-search");
  const locations = parseLines(byId("locations").value).map((line) => {
    const parts = line.split(",").map((part) => part.trim());
    return { city: parts[0], state: parts[1] || "", country: parts[2] || "Brasil" };
  });
  const providers = [...document.querySelectorAll('input[name="provider"]:checked')].map((item) => item.value);
  const payload = {
    business_type: byId("business-type").value.trim(),
    locations,
    quantity: Number(byId("quantity").value),
    quantity_mode: byId("quantity-mode").value,
    providers,
    extra_queries: parseLines(byId("extra-queries").value),
    audit_sites: byId("audit-sites").checked,
    max_audits: Number(byId("max-audits").value),
  };
  button.disabled = true;
  try {
    const result = await api("/api/runs", { method: "POST", body: JSON.stringify(payload) });
    selectedRunId = result.run_id;
    notify(`Busca iniciada (${result.run_id.slice(0, 8)}). O progresso será atualizado automaticamente.`);
    await refreshAll();
  } catch (error) {
    notify(error.message, true);
  } finally { button.disabled = false; }
});

Promise.all([loadProviders(), refreshAll()]).catch((error) => notify(error.message, true));
