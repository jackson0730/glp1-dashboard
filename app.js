const scoreLabels = {
  relevance: "相关性",
  importance: "重要性",
  credibility: "可信度",
  freshness: "新鲜度",
  china_impact: "中国影响"
};

const state = {
  view: "selected",
  query: "",
  category: "",
  news: []
};

const timeline = document.querySelector("#timeline");
const emptyState = document.querySelector("#emptyState");
const dayTemplate = document.querySelector("#dayTemplate");
const cardTemplate = document.querySelector("#cardTemplate");
const searchInput = document.querySelector("#searchInput");
const categoryFilter = document.querySelector("#categoryFilter");
const categoryButtons = document.querySelectorAll("[data-category]");
const appShell = document.querySelector("#appShell");
const mobileMenuToggle = document.querySelector(".mobile-menu-toggle");
const drawerClose = document.querySelector(".drawer-close");
const drawerBackdrop = document.querySelector(".drawer-backdrop");
const mobileQuery = window.matchMedia("(max-width: 860px)");
const themeButtons = document.querySelectorAll("[data-theme-choice]");
const themeColor = document.querySelector("#themeColor");

function applyTheme(theme) {
  const nextTheme = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = nextTheme;
  localStorage.setItem("glp1-theme", nextTheme);
  themeColor.setAttribute("content", nextTheme === "dark" ? "#0b1118" : "#f6f8fb");
  themeButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.themeChoice === nextTheme);
  });
}

applyTheme(localStorage.getItem("glp1-theme") || "light");

function formatDate(value) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    weekday: "short"
  }).format(new Date(value));
}

function formatTime(value) {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    hourCycle: "h23"
  }).format(new Date(value));
}

function formatGeneratedAt(value) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    hourCycle: "h23"
  }).format(new Date(value));
}

function searchableText(item) {
  return [
    item.title,
    item.summary,
    item.source,
    item.region_label,
    item.category_label,
    ...(item.tags || [])
  ].join(" ").toLowerCase();
}

function filteredNews() {
  const query = state.query.trim().toLowerCase();
  return state.news
    .filter((item) => state.view === "all" || item.selected)
    .filter((item) => item.region === "china")
    .filter((item) => !state.category || item.category === state.category)
    .filter((item) => !query || searchableText(item).includes(query))
    .sort((a, b) => new Date(b.published_at) - new Date(a.published_at));
}

function setView(view) {
  state.view = view;
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  if (mobileQuery.matches) setMobileMenu(false);
  render();
}

function setMobileMenu(open) {
  appShell.classList.toggle("mobile-sidebar-open", open);
  mobileMenuToggle.setAttribute("aria-expanded", String(open));
  mobileMenuToggle.setAttribute("aria-label", open ? "收起菜单" : "展开菜单");
}

function toggleSidebarMenu() {
  setMobileMenu(!appShell.classList.contains("mobile-sidebar-open"));
}

function renderScoreGrid(root, scores) {
  root.innerHTML = "";
  Object.entries(scoreLabels).forEach(([key, label]) => {
    const cell = document.createElement("div");
    cell.className = "score-cell";
    const name = document.createElement("span");
    name.textContent = label;
    const value = document.createElement("strong");
    value.textContent = scores?.[key] ?? "--";
    cell.append(name, value);
    root.appendChild(cell);
  });
}

function verificationClass(text) {
  if (text.includes("低可信")) return "low";
  if (text.includes("待") || text.includes("未入")) return "pending";
  return "";
}

function renderTags(root, item) {
  root.innerHTML = "";
  [item.region_label, item.category_label, ...(item.tags || [])].filter(Boolean).slice(0, 7).forEach((tag) => {
    const chip = document.createElement("span");
    chip.className = "tag";
    chip.textContent = tag;
    root.appendChild(chip);
  });
}

function renderRelated(root, button, item) {
  const related = item.related_items || [];
  if (!related.length) return;
  button.hidden = false;
  button.textContent = `相关报道 ${related.length} 条`;
  root.innerHTML = "";
  related.forEach((relatedItem) => {
    const row = document.createElement("div");
    row.className = "related-item";
    const link = document.createElement("a");
    link.href = relatedItem.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = relatedItem.title;
    const meta = document.createElement("small");
    meta.textContent = `${relatedItem.source} · ${formatTime(relatedItem.published_at)} · ${relatedItem.quality_score}`;
    row.append(link, meta);
    root.appendChild(row);
  });
  button.addEventListener("click", () => {
    root.hidden = !root.hidden;
    button.textContent = root.hidden ? `相关报道 ${related.length} 条` : "收起相关报道";
  });
}

function renderCard(item) {
  const fragment = cardTemplate.content.cloneNode(true);
  fragment.querySelector(".time").textContent = formatTime(item.published_at);
  fragment.querySelector(".source").textContent = item.source;

  const selectedBadge = fragment.querySelector(".selected-badge");
  selectedBadge.hidden = !item.selected;

  const verification = fragment.querySelector(".verification");
  verification.textContent = item.verification;
  const verificationState = verificationClass(item.verification);
  if (verificationState) verification.classList.add(verificationState);

  fragment.querySelector(".score").textContent = item.quality_score;

  const title = fragment.querySelector(".title");
  title.textContent = item.title;
  title.href = item.url || "#";

  fragment.querySelector(".summary").textContent = item.summary || "暂无摘要";
  renderTags(fragment.querySelector(".tags"), item);
  renderScoreGrid(fragment.querySelector(".score-grid"), item.scores);
  renderRelated(fragment.querySelector(".related-list"), fragment.querySelector(".related-toggle"), item);
  return fragment;
}

function groupByDate(items) {
  return items.reduce((groups, item) => {
    const key = formatDate(item.published_at);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
    return groups;
  }, new Map());
}

function render() {
  const items = filteredNews();
  timeline.innerHTML = "";
  emptyState.hidden = items.length > 0;
  groupByDate(items).forEach((dayItems, label) => {
    const fragment = dayTemplate.content.cloneNode(true);
    fragment.querySelector("h2").textContent = label;
    fragment.querySelector("span").textContent = `${dayItems.length} 条`;
    const list = fragment.querySelector(".day-items");
    dayItems.forEach((item) => list.appendChild(renderCard(item)));
    timeline.appendChild(fragment);
  });
}

async function boot() {
  const response = await fetch("data/news.json", { cache: "no-store" });
  const payload = await response.json();
  state.news = payload.news || [];
  document.querySelector("#generatedAt").textContent = formatGeneratedAt(payload.generated_at);
  document.querySelector("#eventCount").textContent = `${payload.stats?.events ?? state.news.length} 个`;
  render();
}

searchInput.addEventListener("input", (event) => {
  state.query = event.target.value;
  render();
});

categoryButtons.forEach((button) => {
  button.addEventListener("click", () => {
    state.category = button.dataset.category;
    categoryButtons.forEach((chip) => {
      chip.classList.toggle("active", chip === button);
    });
    render();
  });
});

categoryFilter.addEventListener("keydown", (event) => {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  const chips = Array.from(categoryButtons);
  const currentIndex = chips.findIndex((chip) => chip.classList.contains("active"));
  const direction = event.key === "ArrowRight" ? 1 : -1;
  const next = chips[(currentIndex + direction + chips.length) % chips.length];
  next.focus();
  next.click();
  event.preventDefault();
});

document.querySelectorAll("[data-view]").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});

mobileMenuToggle.addEventListener("click", toggleSidebarMenu);
drawerClose.addEventListener("click", () => setMobileMenu(false));
drawerBackdrop.addEventListener("click", () => setMobileMenu(false));

mobileQuery.addEventListener("change", () => {
  setMobileMenu(false);
});

themeButtons.forEach((button) => {
  button.addEventListener("click", () => applyTheme(button.dataset.themeChoice));
});

boot().catch((error) => {
  timeline.innerHTML = "";
  emptyState.hidden = false;
  emptyState.querySelector("h2").textContent = "数据加载失败";
  emptyState.querySelector("p").textContent = error.message;
});
