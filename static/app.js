import "./vendor/emoji-picker-element/index.js";
import zhCnEmojiI18n from "./vendor/emoji-picker-element/i18n/zh_CN.js";

const uiThemeVersion = "miro-v1";

const state = {
  user: null,
  permissions: {},
  users: [],
  members: [],
  teamPosts: [],
  moments: [],
  momentView: safeStorageGet("teamLoopMomentView", "cards"),
  momentYear: "",
  momentKeyword: "",
  editingMomentId: null,
  activeMomentGalleryId: null,
  activeMomentImageIndex: 0,
  forumCategory: "all",
  forumSearch: "",
  forumSort: "recent",
  forumMineOnly: false,
  forumPage: 1,
  selectedForumPostId: null,
  editingForumPostId: null,
  rules: [],
  machines: [],
  topics: [],
  linkCategories: [],
  links: [],
  meetings: [],
  meetingUsers: [],
  coordinationUsers: [],
  morningItems: [],
  morningUsers: [],
  morningVersionToken: "",
  morningUpdatePending: false,
  morningLoading: false,
  morningLoadId: 0,
  processTemplates: [],
  processInstances: [],
  processScope: "mine",
  processStatus: "active",
  editingProcessTemplateId: null,
  selectedProcessTemplateItemKey: null,
  selectedProcessTemplateId: null,
  selectedProcessTemplateGraphId: null,
  processInstanceViews: {},
  thankUsers: [],
  morningReadOnly: false,
  morningCarriedCount: 0,
  userTypes: [],
  orgUnits: [],
  userFilters: { query: "", org: "", type: "", auth: "" },
  selectedUserIds: new Set(),
  organization: { selected: null, accessible: [] },
  organizationTreeOpen: false,
  organizationTreeSelectionPath: "",
  expandedOrganizationIds: new Set(),
  moduleCatalog: [],
  permissionPreview: null,
  sessions: [],
  settings: [],
  publicSettings: {},
  backups: [],
  auditLogs: [],
  recycleBin: [],
  reminders: [],
  archiveYears: [],
  archiveResults: [],
  shifts: [],
  shiftUsers: [],
  ruleUsers: [],
  activeShiftPopoverDate: null,
  personalMorningMonthItems: [],
  activePersonalMorningChain: null,
  dashboardUsers: [],
  dashboardUserId: null,
  currentPage: "members",
  morningDate: iso(new Date()),
  shiftMonth: new Date(),
  selectedShiftDate: iso(new Date()),
  selectedShiftEndDate: iso(new Date()),
  meetingMonth: new Date(),
  meetingListScope: "week",
  selectedMeetingDate: iso(new Date()),
  selectedMeetingId: null,
  thankYear: new Date().getFullYear(),
  thankScope: "month",
  thankMonth: new Date().getMonth() + 1,
  viewMode: safeStorageGet("teamLoopViewMode", "admin"),
  showLogin: false,
  uiTheme: safeStorageGet("teamLoopThemeVersion", "") === uiThemeVersion
    ? safeStorageGet("teamLoopUiTheme", "miro")
    : "miro",
};

const pages = [
  ["members", "👥", "团队成员", "先看人，再看事。成员档案、职责和团队讨论都在这里。"],
  ["moments", "◈", "团队时刻", "用图片和事迹沉淀团队关键事件。"],
  ["dashboard", "⌂", "工作台", "快速查看团队本周重点数据。"],
  ["archive", "⌕", "搜索归档", "跨年度搜索会议、讨论和早例会事项。"],
  ["morning", "☀", "早例会", "按人追踪当天事项、风险和下一步。"],
  ["processes", "✓", "流程中心", "从团队模板生成个人流程，并按 Checklist 推进。"],
  ["meetings", "▦", "会议沙盘", "按会议沉淀议题、参会签到和行动项。"],
  ["shifts", "◷", "机台排班", "用月历查看白班/夜班，并统计周期工时。"],
  ["rules", "★", "红黑榜", "发布规则、记录积分，并按时间查看排行。"],
  ["thanks", "♥", "Thank You", "每周感谢帮助过自己的团队成员。"],
  ["links", "↗", "常用链接", "归档团队常用系统、文档和工具入口。"],
  ["users", "⚙", "用户管理", "管理员维护账号和权限。"],
  ["system", "▣", "系统管理", "配置、备份和审计日志。"],
];

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const dateFilterPages = new Set(["dashboard", "rules"]);
const uiThemes = new Set(["miro", "feishu", "yuque", "linear", "dingtalk"]);
const teamReactionOptions = ["+1", "👍", "👏", "😊", "🎉", "收到", "辛苦了", "已跟进"];
const momentCategoryMeta = {
  milestone: { label: "里程碑", tone: "milestone" },
  delivery: { label: "项目交付", tone: "delivery" },
  honor: { label: "荣誉认可", tone: "honor" },
  growth: { label: "团队成长", tone: "growth" },
  team: { label: "团队建设", tone: "team" },
};
const forumCategoryMeta = {
  general: { label: "普通讨论", tone: "general" },
  field: { label: "现场问题", tone: "field" },
  retrospective: { label: "经验复盘", tone: "retrospective" },
  roast: { label: "吐槽广场", tone: "roast" },
  announcement: { label: "团队公告", tone: "announcement" },
};
const forumPageSize = 6;
const teamReactionLabels = {
  "+1": "+1",
  "👍": "点赞",
  "👏": "鼓掌",
  "😊": "微笑",
  "🎉": "庆祝",
  "🤑": "赞赏",
  "🤔": "思考",
  "收到": "收到",
  "辛苦了": "辛苦了",
  "已跟进": "已跟进",
};
const teamReactionEmojiAssets = {
  "1f44d": "/vendor/team-reaction-emoji/1f44d.svg",
  "1f44f": "/vendor/team-reaction-emoji/1f44f.svg",
  "1f60a": "/vendor/team-reaction-emoji/1f60a.svg",
  "1f389": "/vendor/team-reaction-emoji/1f389.svg",
  "1f911": "/vendor/team-reaction-emoji/1f911.svg",
  "1f914": "/vendor/team-reaction-emoji/1f914.svg",
};
const teamReactionEmojiDataSource = "/vendor/emoji-picker-element-data/zh/emojibase/data.json";
let activeReactionTarget = null;
let pendingLinkDeleteId = null;
let activePageRefreshId = 0;
let authSyncInFlight = false;
let lastAuthSyncAt = 0;

function safeStorageGet(key, fallback) {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}

function safeStorageSet(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Theme preference is cosmetic; ignore storage failures.
  }
}

function safeSessionGet(key, fallback = "") {
  try {
    return sessionStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}

function safeSessionSet(key, value) {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    // Authentication fallback still works when session storage is unavailable.
  }
}

function safeSessionRemove(key) {
  try {
    sessionStorage.removeItem(key);
  } catch {
    // Ignore storage failures.
  }
}

function organizationPathFromLocation() {
  const match = window.location.pathname.match(/^\/org\/(.+?)\/?$/i);
  return match ? decodeURIComponent(match[1]).replace(/^\/+|\/+$/g, "").toLowerCase() : "";
}

function pageFromLocation() {
  const requested = new URL(window.location.href).searchParams.get("view") || "";
  return pages.some(([id]) => id === requested) ? requested : "";
}

function updatePageInLocation(id, mode = "replace") {
  const url = new URL(window.location.href);
  url.searchParams.set("view", id);
  const target = `${url.pathname}${url.search}${url.hash}`;
  if (mode === "push") window.history.pushState({}, "", target);
  else window.history.replaceState({}, "", target);
}

function currentSsoReturnTo() {
  const url = new URL(window.location.href);
  url.searchParams.delete("sso");
  url.searchParams.delete("sso_error");
  url.searchParams.set("view", pageFromLocation() || state.currentPage || "members");
  return `${url.pathname}${url.search}`;
}

function ssoLoginUrl() {
  return `/api/sso/login?return_to=${encodeURIComponent(currentSsoReturnTo())}`;
}

function selectedOrganizationPath() {
  return state.organization?.selected?.path || organizationPathFromLocation();
}

function applyOrganizationData(data, updateRoute = true) {
  state.organization = data || { selected: null, accessible: [] };
  const selected = state.organization.selected;
  if (updateRoute && selected?.route && window.location.pathname !== `${selected.route}/` && window.location.pathname !== selected.route) {
    window.history.replaceState({}, "", `${selected.route}${window.location.search}${window.location.hash}`);
  }
  renderOrganizationSwitcher();
}

function syncOrganizationTreeExpansion(units, selected) {
  const selectedPath = selected?.path || "";
  if (state.organizationTreeSelectionPath === selectedPath) return;
  const byId = new Map(units.map((unit) => [Number(unit.id), unit]));
  const expanded = new Set();
  const visited = new Set();
  let current = selected;
  while (current && !visited.has(Number(current.id))) {
    const currentId = Number(current.id);
    expanded.add(currentId);
    visited.add(currentId);
    current = byId.get(Number(current.parent_id));
  }
  state.expandedOrganizationIds = expanded;
  state.organizationTreeSelectionPath = selectedPath;
}

function organizationTreeMarkup(units, selected) {
  const byId = new Map(units.map((unit) => [Number(unit.id), unit]));
  const children = new Map();
  units.forEach((unit) => {
    const parentId = byId.has(Number(unit.parent_id)) ? Number(unit.parent_id) : null;
    if (!children.has(parentId)) children.set(parentId, []);
    children.get(parentId).push(unit);
  });

  const renderNodes = (nodes, depth = 0) => `<ul role="${depth === 0 ? "tree" : "group"}">${nodes.map((unit) => {
    const unitId = Number(unit.id);
    const childUnits = children.get(unitId) || [];
    const hasChildren = childUnits.length > 0;
    const expanded = hasChildren && state.expandedOrganizationIds.has(unitId);
    const active = unit.path === selected?.path;
    const label = unit.label_path || unit.name;
    return `<li role="treeitem" aria-level="${depth + 1}"${hasChildren ? ` aria-expanded="${expanded}"` : ""}>
      <div class="org-tree-node ${active ? "active" : ""}" style="--org-tree-depth:${depth}">
        ${hasChildren
          ? `<button class="org-tree-branch-toggle" type="button" data-org-tree-expand="${unitId}" aria-label="${expanded ? "收起" : "展开"}${escapeHtml(unit.name)}" title="${expanded ? "收起" : "展开"}${escapeHtml(unit.name)}">${expanded ? "−" : "+"}</button>`
          : '<span class="org-tree-branch-spacer" aria-hidden="true"></span>'}
        <button class="org-tree-select" type="button" data-org-path="${escapeHtml(unit.path)}" title="${escapeHtml(label)}" ${active ? 'aria-current="page"' : ""}>
          <span>${escapeHtml(unit.name)}</span>
          ${active ? '<small aria-hidden="true">当前</small>' : ""}
        </button>
      </div>
      ${expanded ? renderNodes(childUnits, depth + 1) : ""}
    </li>`;
  }).join("")}</ul>`;

  return renderNodes(children.get(null) || []);
}

function renderOrganizationSwitcher() {
  const wrapper = $("#orgSwitcher");
  const trigger = $("#orgTreeToggle");
  const panel = $("#orgTreePanel");
  const tree = $("#orgTreeList");
  if (!wrapper || !trigger || !panel || !tree) return;
  const units = state.organization?.accessible || [];
  const selected = state.organization?.selected;
  wrapper.classList.toggle("hidden", units.length === 0);
  syncOrganizationTreeExpansion(units, selected);
  const selectedLabel = selected?.label_path || selected?.name || "";
  const currentPath = $("#orgCurrentPath");
  if (currentPath) {
    currentPath.textContent = selectedLabel;
    currentPath.title = selectedLabel;
  }
  trigger.title = selectedLabel ? `当前：${selectedLabel}` : "切换团队";
  trigger.disabled = units.length < 2;
  trigger.setAttribute("aria-expanded", String(state.organizationTreeOpen));
  wrapper.classList.toggle("tree-open", state.organizationTreeOpen);
  panel.classList.toggle("hidden", !state.organizationTreeOpen);
  $("#orgTreeChevron").textContent = state.organizationTreeOpen ? "⌃" : "⌄";
  tree.innerHTML = organizationTreeMarkup(units, selected);
}

async function selectOrganizationPath(path) {
  const unit = state.organization?.accessible?.find((item) => item.path === path);
  if (!unit) return;
  state.organizationTreeOpen = false;
  if (unit.path === state.organization?.selected?.path) {
    renderOrganizationSwitcher();
    return;
  }
  const url = new URL(window.location.href);
  url.pathname = unit.route;
  url.searchParams.set("view", state.currentPage);
  window.history.pushState({}, "", `${url.pathname}${url.search}${url.hash}`);
  state.organization.selected = unit;
  renderOrganizationSwitcher();
  state.thankUsers = [];
  state.morningItems = [];
  state.morningUsers = [];
  state.meetingUsers = [];
  state.coordinationUsers = [];
  state.shiftUsers = [];
  state.ruleUsers = [];
  state.morningVersionToken = "";
  state.morningUpdatePending = false;
  await refreshAll();
}

function applyUiTheme() {
  const theme = uiThemes.has(state.uiTheme) ? state.uiTheme : "miro";
  state.uiTheme = theme;
  document.body.dataset.theme = theme;
  safeStorageSet("teamLoopThemeVersion", uiThemeVersion);
  safeStorageSet("teamLoopUiTheme", theme);
  const select = $("#themeSelect");
  if (select) select.value = theme;
}

function setUiTheme(theme) {
  state.uiTheme = uiThemes.has(theme) ? theme : "miro";
  safeStorageSet("teamLoopUiTheme", state.uiTheme);
  applyUiTheme();
}

function isAdminAccount() {
  return Boolean(state.permissions?.isAdmin);
}

function isAdminView() {
  return isAdminAccount() && state.viewMode !== "user" && !state.permissionPreview;
}

function isGuest() {
  return !state.user;
}

function canAccessPage(id) {
  if (state.permissionPreview) return state.permissionPreview.modules.includes(id);
  if (isGuest()) return Array.isArray(state.permissions?.modules) && state.permissions.modules.includes(id);
  if (isAdminView()) return true;
  if (["users", "system"].includes(id)) return false;
  const modules = state.permissions?.modules;
  if (!Array.isArray(modules)) return true;
  return modules.includes(id);
}

function canManageLinks() {
  return canOperate("links", "edit") || canOperate("links", "delete");
}

function canOperate(moduleKey, action = "view") {
  if (state.permissionPreview) return Boolean(state.permissionPreview.operations?.[moduleKey]?.[action]);
  if (isAdminAccount()) return true;
  const operations = state.permissions?.operations;
  if (!operations || !operations[moduleKey]) return action === "view" ? canAccessPage(moduleKey) : false;
  return Boolean(operations[moduleKey][action]);
}

function firstAccessiblePage() {
  return pages.find(([id]) => canAccessPage(id))?.[0] || "members";
}

function canLoadModule(id) {
  return canAccessPage(id) || isAdminView();
}

function setViewMode(mode) {
  state.viewMode = mode === "user" ? "user" : "admin";
  safeStorageSet("teamLoopViewMode", state.viewMode);
}

function permissionOperations(type) {
  const operations = {};
  state.moduleCatalog.forEach((module) => {
    const source = type?.permissions?.[module.key] || {};
    operations[module.key] = {
      view: Boolean(source.view),
      create: Boolean(source.create),
      edit: Boolean(source.edit),
      delete: Boolean(source.delete),
    };
  });
  return operations;
}

function enterPermissionPreview(typeKey, proposedPermissions = null, proposedName = "") {
  const type = state.userTypes.find((item) => item.key === typeKey);
  if (!type) return;
  const operations = permissionOperations({ ...type, permissions: proposedPermissions || type.permissions });
  const modules = Object.entries(operations).filter(([, actions]) => actions.view).map(([key]) => key);
  if (!modules.length) {
    toast("该类型当前没有可查看模块，请先勾选查看权限");
    return;
  }
  state.permissionPreview = {
    key: type.key,
    name: proposedName || type.name,
    operations,
    modules,
  };
  setViewMode("user");
  applyAuthView();
  switchPage(firstAccessiblePage());
  refreshAll().catch((error) => toast(error.message));
}

function exitPermissionPreview() {
  state.permissionPreview = null;
  setViewMode("admin");
  applyAuthView();
  switchPage("users");
  refreshAll().catch((error) => toast(error.message));
}

function escapeHtml(value = "") {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[char]);
}

function iso(date) {
  const value = new Date(date);
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function shortDate(value) {
  if (!value) return "";
  const date = new Date(String(value).replace(" ", "T"));
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10);
  const sameYear = date.getFullYear() === new Date().getFullYear();
  const prefix = sameYear ? "" : `${date.getFullYear()}年`;
  return `${prefix}${date.getMonth() + 1}月${date.getDate()}日`;
}

function compactDate(value) {
  if (!value) return "";
  const date = new Date(String(value).replace(" ", "T"));
  if (Number.isNaN(date.getTime())) return String(value).slice(5, 10).replace("-", "/");
  const sameYear = date.getFullYear() === new Date().getFullYear();
  const prefix = sameYear ? "" : `${date.getFullYear()}/`;
  return `${prefix}${date.getMonth() + 1}/${date.getDate()}`;
}

function shortDateTime(value) {
  if (!value) return "";
  const date = new Date(String(value).replace(" ", "T"));
  if (Number.isNaN(date.getTime())) return String(value).replace("T", " ").slice(0, 16);
  const time = `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
  return `${shortDate(value)} ${time}`;
}

function isTodayValue(value) {
  return String(value || "").slice(0, 10) === iso(new Date());
}

function mondayOf(value) {
  const d = new Date(value);
  const day = d.getDay() || 7;
  d.setDate(d.getDate() - day + 1);
  return iso(d);
}

function addDays(value, days) {
  const date = new Date(value);
  date.setDate(date.getDate() + days);
  return date;
}

function monthStart(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function monthEnd(date) {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0);
}

function setDefaultDates() {
  const now = new Date();
  const today = iso(now);
  $("#fromDate").value = $("#fromDate").value || iso(monthStart(now));
  $("#toDate").value = $("#toDate").value || today;
  $$('input[type="date"]').forEach((input) => {
    if (!input.value) input.value = today;
  });
  const shiftStartDate = $('input[name="shift_start_date"]');
  const shiftEndDate = $('input[name="shift_end_date"]');
  if (shiftStartDate) shiftStartDate.value = state.selectedShiftDate;
  if (shiftEndDate && !shiftEndDate.value) shiftEndDate.value = state.selectedShiftEndDate;
  const meetingDate = $('input[name="meeting_date"]');
  if (meetingDate) meetingDate.value = state.selectedMeetingDate;
  const morningDate = $("#morningDate");
  if (morningDate && !morningDate.value) morningDate.value = state.morningDate;
  const generateStart = $('input[name="start_date"]');
  if (generateStart) generateStart.value = mondayOf(state.selectedMeetingDate);
}

async function api(path, options = {}) {
  const orgPath = selectedOrganizationPath();
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(orgPath ? { "X-Team-Org-Path": orgPath } : {}), ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || "请求失败");
    error.status = response.status;
    error.data = data;
    if (response.status === 401 && state.user && path !== "/api/login") {
      transitionToLoggedOut(true, true).catch(() => {});
    }
    throw error;
  }
  return data;
}

function formData(form) {
  const data = Object.fromEntries(new FormData(form).entries());
  Object.keys(data).forEach((key) => {
    if (data[key] === "" || data[key] instanceof File) delete data[key];
  });
  return data;
}

function fullFormData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    if (!file || !file.size) return resolve("");
    if (!file.type.startsWith("image/")) return resolve("");
    const image = new Image();
    const url = URL.createObjectURL(file);
    image.onload = () => {
      const maxSize = 320;
      const scale = Math.min(1, maxSize / Math.max(image.width, image.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(image.width * scale));
      canvas.height = Math.max(1, Math.round(image.height * scale));
      const context = canvas.getContext("2d");
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL("image/jpeg", 0.82));
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("头像图片读取失败"));
    };
    image.src = url;
  });
}

function momentFileToData(file) {
  return new Promise((resolve, reject) => {
    if (!file || !file.size) return resolve(null);
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) return reject(new Error("仅支持 JPG、PNG 或 WebP 图片"));
    if (file.size > 12 * 1024 * 1024) return reject(new Error("原始图片不能超过 12 MB"));
    const image = new Image();
    const url = URL.createObjectURL(file);
    image.onload = () => {
      const maxEdge = 1800;
      const scale = Math.min(1, maxEdge / Math.max(image.width, image.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(image.width * scale));
      canvas.height = Math.max(1, Math.round(image.height * scale));
      const context = canvas.getContext("2d");
      context.fillStyle = "#ffffff";
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      resolve({ name: file.name, data_url: canvas.toDataURL("image/jpeg", 0.86) });
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error(`无法读取图片：${file.name}`));
    };
    image.src = url;
  });
}

async function momentFilesToData(fileList) {
  const files = [...(fileList || [])];
  if (files.length > 6) throw new Error("每条团队时刻最多上传 6 张图片");
  return (await Promise.all(files.map(momentFileToData))).filter(Boolean);
}

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.remove("hidden");
  clearTimeout(window.__toastTimer);
  const duration = Math.min(9000, Math.max(2200, String(message).length * 90));
  window.__toastTimer = setTimeout(() => el.classList.add("hidden"), duration);
}

function periodQuery() {
  return `from=${encodeURIComponent($("#fromDate").value)}&to=${encodeURIComponent($("#toDate").value)}`;
}

function thankPeriodRange() {
  if (state.thankScope === "year") {
    return {
      from: `${state.thankYear}-01-01`,
      to: `${state.thankYear}-12-31`,
      label: `${state.thankYear} 年全年`,
    };
  }
  const start = new Date(state.thankYear, state.thankMonth - 1, 1);
  const end = monthEnd(start);
  return {
    from: iso(start),
    to: iso(end),
    label: `${state.thankYear} 年 ${state.thankMonth} 月`,
  };
}

function thankPeriodQuery() {
  const range = thankPeriodRange();
  return `from=${encodeURIComponent(range.from)}&to=${encodeURIComponent(range.to)}`;
}

function shiftPeriodQuery() {
  const start = monthStart(state.shiftMonth);
  const end = monthEnd(state.shiftMonth);
  return `from=${iso(start)}&to=${iso(end)}`;
}

function meetingPeriodQuery() {
  const start = monthStart(state.meetingMonth);
  const end = monthEnd(state.meetingMonth);
  return `from=${iso(start)}&to=${iso(end)}`;
}

function renderPageToolbar(id = state.currentPage) {
  const toolbar = $("#pageToolbar");
  if (!toolbar) return;
  const periodControls = $("#periodControls");
  const showDateFilter = dateFilterPages.has(id);
  toolbar.classList.toggle("toolbar-compact", !showDateFilter);
  if (periodControls) periodControls.classList.toggle("hidden", !showDateFilter);
}

function applyAuthView() {
  if (state.user && !isAdminAccount()) setViewMode("user");
  const guest = isGuest();
  const showLogin = guest && state.showLogin;
  $("#loginView").classList.toggle("hidden", !showLogin);
  $("#appView").classList.toggle("hidden", showLogin);
  const roleText = state.user?.role === "admin"
    ? "管理员"
    : state.user?.classification_pending
      ? "待管理员分类"
      : (state.user?.user_type_name || "类型用户");
  const modeText = isAdminAccount() ? (isAdminView() ? "管理视图" : "用户视图") : "";
  const orgText = state.organization?.selected?.name || state.user?.org_unit_name || "";
  $("#currentUser").textContent = state.user ? `${state.user.display_name} · ${roleText}${orgText ? ` · ${orgText}` : ""}${modeText ? ` · ${modeText}` : ""}` : "访客 · 只读";
  renderOrganizationSwitcher();
  $("#logoutBtn")?.classList.toggle("hidden", guest);
  $("#passwordBtn")?.classList.toggle("hidden", guest);
  $("#loginEntryBtn")?.classList.toggle("hidden", !guest || showLogin);
  $("#reminderBtn")?.classList.toggle("hidden", guest);
  const viewModeBtn = $("#viewModeBtn");
  if (viewModeBtn) {
    viewModeBtn.classList.toggle("hidden", !isAdminAccount());
    viewModeBtn.textContent = isAdminView() ? "切换用户视图" : "切换管理视图";
  }
  const previewBanner = $("#permissionPreviewBanner");
  previewBanner?.classList.toggle("hidden", !state.permissionPreview);
  if (state.permissionPreview) {
    $("#permissionPreviewTitle").textContent = `正在预览：${state.permissionPreview.name}`;
    $("#permissionPreviewSummary").textContent = `可查看 ${state.permissionPreview.modules.length} 个模块，服务端仍保持管理员身份`;
  }
  $$(".admin-only").forEach((el) => el.classList.toggle("hidden", !isAdminView()));
  $("#forumCreateButton")?.classList.toggle("hidden", guest || !canOperate("members", "create"));
  $("#momentCreateButton")?.classList.toggle("hidden", guest || !canOperate("moments", "create"));
  $$('[data-forum-create-open]').forEach((button) => button.classList.toggle("hidden", guest || !canOperate("members", "create")));
  $("#forumMineButton")?.classList.toggle("hidden", guest);
  $$('[data-admin-category]').forEach((option) => {
    option.hidden = !isAdminView();
    option.disabled = !isAdminView();
  });
  $("#thankForm")?.closest(".panel")?.classList.toggle("hidden", guest || !canOperate("thanks", "create"));
  $("#linkForm")?.closest(".panel")?.classList.toggle("hidden", guest || !canOperate("links", "create"));
  $("#openMeetingCreateBtn")?.classList.toggle("hidden", guest || !canOperate("meetings", "create"));
  const cannotJoinMorning = !isAdminView() && state.user?.eligible_morning !== undefined && !Boolean(state.user.eligible_morning);
  $("#morningCreatePanel")?.classList.toggle("hidden", guest || cannotJoinMorning || !canOperate("morning", "create"));
  $("#personalMorningCreateForm")?.classList.toggle("hidden", guest || cannotJoinMorning || !canOperate("morning", "create"));
  if (!canAccessPage(state.currentPage)) {
    switchPage(firstAccessiblePage());
  } else {
    renderPageToolbar();
    renderNav();
  }
}

async function transitionToLoggedOut(showLogin = true, refresh = true) {
  closeUserTypePermissionModal();
  closeUserAccountModal();
  state.user = null;
  state.permissions = {};
  state.permissionPreview = null;
  state.sessions = [];
  state.thankUsers = [];
  state.showLogin = showLogin;
  applyBranding();
  applyAuthView();
  if (showLogin && maybeStartSsoAutoLogin()) return;
  if (refresh) await refreshAll();
}

async function syncAuthState(force = false) {
  if (authSyncInFlight) return;
  const now = Date.now();
  if (!force && now - lastAuthSyncAt < 15000) return;
  authSyncInFlight = true;
  lastAuthSyncAt = now;
  try {
    const data = await api("/api/me");
    if (state.user && !data.user) {
      await transitionToLoggedOut(true, true);
      toast("登录状态已结束，请重新登录");
      return;
    }
    if (data.user) {
      const changedUser = !state.user || Number(state.user.id) !== Number(data.user.id);
      state.user = data.user;
      state.permissions = data.permissions || {};
      state.publicSettings = data.settings || state.publicSettings;
      applyOrganizationData(data.organization || state.organization);
      applyAuthView();
      if (changedUser) await refreshAll();
    }
  } finally {
    authSyncInFlight = false;
  }
}

function renderNav() {
  $("#nav").innerHTML = pages
    .filter(([id]) => canAccessPage(id))
    .map(([id, icon, title]) => `<button class="nav-item ${state.currentPage === id ? "active" : ""}" data-page="${id}"><span>${icon}</span>${title}</button>`)
    .join("");
  requestAnimationFrame(() => {
    const nav = $("#nav");
    const active = nav?.querySelector(".nav-item.active");
    if (!nav || !active || nav.scrollWidth <= nav.clientWidth) return;
    const left = active.offsetLeft - (nav.clientWidth - active.offsetWidth) / 2;
    nav.scrollTo({ left: Math.max(0, left), behavior: "smooth" });
  });
}

function setSidebarAccountExpanded(expanded) {
  const userBox = $(".user-box");
  const button = $("#sidebarAccountToggle");
  if (!userBox || !button) return;
  userBox.classList.toggle("account-open", expanded);
  button.setAttribute("aria-expanded", expanded ? "true" : "false");
  button.textContent = expanded ? "收起" : "账户";
}

function switchPage(id, updateRoute = true) {
  if (!canAccessPage(id)) id = firstAccessiblePage();
  if (isGuest()) {
    state.showLogin = false;
    $("#loginView")?.classList.add("hidden");
    $("#appView")?.classList.remove("hidden");
    $("#loginEntryBtn")?.classList.remove("hidden");
  }
  state.currentPage = id;
  if (updateRoute) updatePageInLocation(id);
  $$(".page").forEach((page) => page.classList.toggle("active", page.id === id));
  const meta = pages.find((page) => page[0] === id);
  $("#pageTitle").textContent = meta?.[2] || "团队成员";
  $("#pageDesc").textContent = meta?.[3] || "";
  renderPageToolbar(id);
  renderNav();
  if (window.matchMedia("(max-width: 900px)").matches) {
    setSidebarAccountExpanded(false);
  }
}

async function loadReferenceData() {
  const tasks = [];
  tasks.push(api("/api/org-context").then((data) => applyOrganizationData(data)));
  if (canLoadModule("members")) {
    tasks.push(api("/api/members").then((data) => { state.members = data.members; }));
  } else {
    state.members = [];
  }
  if (canLoadModule("rules")) {
    tasks.push(api("/api/rules").then((data) => { state.rules = data.rules; }));
  } else {
    state.rules = [];
  }
  if (canLoadModule("shifts")) {
    tasks.push(api("/api/machines").then((data) => { state.machines = data.machines; }));
  } else {
    state.machines = [];
  }
  if (canLoadModule("links")) {
    tasks.push(api("/api/link-categories").then((data) => { state.linkCategories = data.categories; }));
  } else {
    state.linkCategories = [];
  }
  if (canLoadModule("meetings")) {
    tasks.push(api("/api/meeting-topics").then((data) => { state.topics = data.types; }));
  } else {
    state.topics = [];
  }
  if (isAdminView()) {
    tasks.push(api("/api/users").then((data) => { state.users = data.users; }));
    tasks.push(api("/api/org-units").then((data) => { state.orgUnits = data.units || []; renderOrgUnits(); }));
    tasks.push(api("/api/user-types").then((data) => {
      state.userTypes = data.types;
      state.moduleCatalog = data.modules;
    }));
  } else {
    state.users = [];
    state.orgUnits = state.organization?.accessible || [];
  }
  if (!isGuest()) {
    tasks.push(loadReminders());
  } else {
    state.reminders = [];
    renderReminders(0);
  }
  await Promise.all(tasks);
  if (!isAdminView() && state.members.length) {
    state.users = state.members
      .filter((member) => member.user_id)
      .map((member) => ({ id: member.user_id, display_name: member.linked_user || member.name, active: 1, role: "user" }));
  }
  populateSelects();
}

function populateSelects() {
  const selectUsers = state.users.length ? state.users : state.morningUsers.map((user) => ({ ...user, active: 1 }));
  const activeUsers = selectUsers.filter((user) => user.active !== 0);
  const userOptions = activeUsers.map((user) => `<option value="${user.id}">${escapeHtml(user.display_name)}</option>`).join("");
  const morningUsers = state.morningUsers;
  const morningOptions = morningUsers.map((user) => `<option value="${user.id}">${escapeHtml(user.display_name)}</option>`).join("");
  const ruleUsers = state.ruleUsers;
  const shiftUsers = state.shiftUsers;
  const ruleOptionsUsers = ruleUsers.map((user) => `<option value="${user.id}">${escapeHtml(user.display_name)}</option>`).join("");
  const shiftOptionsUsers = shiftUsers.map((user) => `<option value="${user.id}">${escapeHtml(user.display_name)}</option>`).join("");
  const userOptional = `<option value="">不绑定账号</option>${userOptions}`;
  const ruleOptions = `<option value="">不关联规则</option>${state.rules.map((rule) => `<option value="${rule.id}">${rule.kind === "red" ? "红" : "黑"} · ${escapeHtml(rule.title)}</option>`).join("")}`;
  const machineOptions = state.machines.map((machine) => `<option value="${machine.id}">${escapeHtml(machine.name)}</option>`).join("");
  const thankUsers = state.thankUsers.filter((user) => user.id !== state.user?.id);
  const thankUserLabel = (user) => user.org_unit_name ? `${user.display_name} · ${user.org_unit_name}` : user.display_name;
  const thankOptions = thankUsers.map((user) => `<option value="${user.id}">${escapeHtml(thankUserLabel(user))}</option>`).join("");
  const topicOptions = state.topics.map((topic) => `<option value="${topic.id}">${escapeHtml(topic.name)}</option>`).join("");
  const linkCategoryOptions = state.linkCategories.map((category) => `<option value="${escapeHtml(category.name)}">${escapeHtml(category.name)}</option>`).join("");
  const accountTypes = state.userTypes.filter((type) => !type.is_guest && type.key !== "guest");
  const userTypeOptions = accountTypes.map((type) => `<option value="${escapeHtml(type.key)}">${escapeHtml(type.name)}</option>`).join("");
  const orgOptions = (state.orgUnits.length ? state.orgUnits : (state.organization?.accessible || []))
    .map((unit) => `<option value="${unit.id}">${"　".repeat(Number(unit.depth || 0))}${escapeHtml(unit.name)}</option>`).join("");
  const userTypeCopyOptions = `<option value="">不复制权限</option>${accountTypes.map((type) => `<option value="${escapeHtml(type.key)}">复制 ${escapeHtml(type.name)} 权限</option>`).join("")}`;

  $$("[data-users]").forEach((select) => { select.innerHTML = userOptions; });
  $$("[data-morning-users]").forEach((select) => { select.innerHTML = morningOptions; });
  $$("[data-rule-users]").forEach((select) => { select.innerHTML = ruleOptionsUsers; });
  $$("[data-shift-users]").forEach((select) => { select.innerHTML = shiftOptionsUsers; });
  $$("[data-user-types]").forEach((select) => { select.innerHTML = userTypeOptions; });
  $$("[data-org-units]").forEach((select) => { select.innerHTML = orgOptions; });
  $$("[data-user-type-copy]").forEach((select) => { select.innerHTML = userTypeCopyOptions; });
  updateUserBulkActionOptions();
  $$("[data-users-optional]").forEach((select) => { select.innerHTML = userOptional; });
  $$("[data-rules]").forEach((select) => { select.innerHTML = ruleOptions; });
  $$("[data-machines]").forEach((select) => { select.innerHTML = machineOptions; });
  $$("[data-thank-users]").forEach((select) => { select.innerHTML = thankOptions; });
  $$("[data-thank-users-checklist]").forEach((box) => {
    const form = box.closest("form");
    const selected = form ? new Set(new FormData(form).getAll("receiver_ids").map(String)) : new Set();
    const selectedNames = thankUsers
      .filter((user) => selected.has(String(user.id)))
      .map((user) => thankUserLabel(user));
    box.innerHTML = `
      <summary class="thank-recipient-summary">
        <span data-thank-selected-label>${escapeHtml(selectedNames.length ? selectedNames.join("、") : "选择感谢对象（可多选）")}</span>
        <strong data-thank-selected-count>${selectedNames.length} 人</strong>
      </summary>
      <div class="thank-recipient-menu">
        ${thankUsers.length
          ? thankUsers.map((user) => `
            <label class="check-chip">
              <input type="checkbox" name="receiver_ids" value="${user.id}" data-name="${escapeHtml(user.display_name)}" ${selected.has(String(user.id)) ? "checked" : ""}>
              <span>${escapeHtml(thankUserLabel(user))}</span>
            </label>`).join("")
          : '<p class="empty-note">暂无可感谢成员</p>'}
      </div>`;
  });
  $$("[data-topic-types]").forEach((select) => { select.innerHTML = topicOptions; });
  $$("[data-owner-users]").forEach((select) => {
    const current = select.value;
    select.innerHTML = renderUserOptions(current, "默认负责人", state.coordinationUsers);
    select.value = state.coordinationUsers.some((user) => Number(user.id) === Number(current)) ? current : "";
  });
  $$("[data-link-categories], [data-link-edit-categories]").forEach((select) => { select.innerHTML = linkCategoryOptions || '<option value="通用">通用</option>'; });
  const linkFilter = $("#linkCategoryFilter");
  if (linkFilter) {
    const current = linkFilter.value;
    linkFilter.innerHTML = `<option value="">全部分类</option>${linkCategoryOptions}`;
    linkFilter.value = state.linkCategories.some((category) => category.name === current) ? current : "";
  }
  const categoryList = $("#linkCategoryList");
  if (categoryList) {
    categoryList.innerHTML = state.linkCategories.length
      ? state.linkCategories.map((category) => `<span class="chip">${escapeHtml(category.name)}</span>`).join("")
      : "<p>暂无分类</p>";
  }
}

function table(headers, rows) {
  if (!rows.length) return "<p>暂无数据</p>";
  return `<table><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function renderRank(items, field, unit) {
  if (!items.length) return `<p>暂无数据</p>`;
  return items.map((item, index) => {
    const name = item.display_name || item.machine_name || "未命名";
    return `<div class="rank-row"><span class="rank-no">${index + 1}</span><strong>${escapeHtml(name)}</strong><span>${Number(item[field] || 0)} ${unit}</span></div>`;
  }).join("");
}

function renderThankRank(items = []) {
  if (!items.length) return `<p>暂无数据</p>`;
  return items.map((item, index) => `
    <div class="rank-row thank-rank-row">
      <span class="rank-no">${index + 1}</span>
      <strong>${escapeHtml(item.display_name || "未命名")}</strong>
      ${index < 3 ? '<span class="thank-rank-heart" aria-label="Thank You 之星">♥</span>' : ""}
      <span>${Number(item.thanks || 0)} 次</span>
    </div>`).join("");
}

function settingValue(key, fallback = "") {
  const setting = state.settings.find((item) => item.key === key);
  if (setting) return setting.value;
  return state.publicSettings?.[key] ?? fallback;
}

function settingEnabled(key, fallback = true) {
  return String(settingValue(key, fallback ? "1" : "0")) !== "0";
}

function applyBranding() {
  const brandName = settingValue("app_brand_name", "Team Loop") || "Team Loop";
  const teamName = settingValue("app_team_name", "技术项目团队") || "技术项目团队";
  const mark = brandName.trim().slice(0, 1).toUpperCase() || "T";
  const brandNameEl = $("#brandName");
  const brandTeamEl = $("#brandTeam");
  const brandMarkEl = $("#brandMark");
  if (brandNameEl) brandNameEl.textContent = brandName;
  if (brandTeamEl) brandTeamEl.textContent = teamName;
  if (brandMarkEl) brandMarkEl.textContent = mark;
  const ssoSection = $("#ssoLoginSection");
  const ssoButton = $("#ssoLoginBtn");
  const ssoMode = settingValue("sso_mode", "discovery");
  const configuredInAdminView = settingEnabled("sso_enabled", false)
    && Boolean(settingValue("sso_client_id"))
    && (ssoMode === "manual"
      ? Boolean(settingValue("sso_authorization_url")) && Boolean(settingValue("sso_token_url")) && Boolean(settingValue("sso_userinfo_url"))
      : Boolean(settingValue("sso_issuer_url")));
  const ssoReady = String(state.publicSettings?.sso_ready || "0") === "1" || configuredInAdminView;
  if (ssoSection) ssoSection.classList.toggle("hidden", !ssoReady);
  if (ssoButton) ssoButton.textContent = settingValue("sso_button_label", "企业 SSO 登录") || "企业 SSO 登录";
  const insecureTransport = settingValue("https_required", "0") === "1" && window.location.protocol !== "https:";
  $("#loginTransportWarning")?.classList.toggle("hidden", !insecureTransport);
  const localLoginForm = $("#loginForm");
  if (localLoginForm) {
    localLoginForm.querySelectorAll("input, button").forEach((element) => { element.disabled = insecureTransport; });
  }
  document.title = `${teamName}周例会`;
}

function handleSsoCallbackNotice() {
  const url = new URL(window.location.href);
  const success = url.searchParams.get("sso") === "success";
  const error = url.searchParams.get("sso_error");
  if (!success && !error) return "";
  url.searchParams.delete("sso");
  url.searchParams.delete("sso_error");
  window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  if (success) {
    safeSessionRemove("teamLoopSsoAttempted");
    safeSessionRemove("teamLoopSsoSkip");
    toast("企业 SSO 登录成功");
    return "success";
  }
  safeSessionRemove("teamLoopSsoAttempted");
  safeSessionSet("teamLoopSsoSkip", "1");
  state.showLogin = true;
  applyAuthView();
  toast(`企业 SSO 登录失败：${error}`);
  return "error";
}

function maybeStartSsoAutoLogin(callbackState = "") {
  const ready = String(state.publicSettings?.sso_ready || "0") === "1";
  const automatic = String(state.publicSettings?.sso_auto_login || "0") === "1";
  if (state.user || !ready || !automatic || callbackState === "error") return false;
  if (safeSessionGet("teamLoopSsoSkip") === "1" || safeSessionGet("teamLoopSsoAttempted") === "1") return false;
  safeSessionSet("teamLoopSsoAttempted", "1");
  window.location.replace(ssoLoginUrl());
  return true;
}

function formatBytes(value = 0) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function isMyMorningItem(item) {
  return Number(item.owner_id) === Number(state.dashboardUserId || state.user?.id);
}

function sortMorningForWorkbench(items = []) {
  return [...items].sort((a, b) => {
    const score = (item) => (item.status === "risk" ? 4 : 0)
      + (item.blocker ? 3 : 0)
      + (isMorningDue(item) ? 2 : 0)
      + (item.priority === "high" ? 1 : 0);
    return score(b) - score(a) || String(a.title || "").localeCompare(String(b.title || ""), "zh-CN");
  });
}

function dateListBetween(startValue, endValue) {
  const start = new Date(startValue);
  const end = new Date(endValue);
  const dates = [];
  for (let date = new Date(start); date <= end; date.setDate(date.getDate() + 1)) {
    dates.push(iso(date));
  }
  return dates;
}

function morningChainId(item) {
  return String(item.root_id || item.id || `${item.owner_id}-${item.title}`);
}

function hashIndex(value, size) {
  const text = String(value || "");
  let hash = 0;
  for (let index = 0; index < text.length; index += 1) {
    hash = (hash * 31 + text.charCodeAt(index)) % 9973;
  }
  return Math.abs(hash) % size;
}

const personalLineColors = ["#3370ff", "#12b981", "#f59e0b", "#8b5cf6", "#ef4444", "#0ea5e9", "#14b8a6", "#f97316"];

function latestByMorningChain(items = []) {
  const map = new Map();
  items.forEach((item) => {
    const key = morningChainId(item);
    const current = map.get(key);
    if (!current || String(item.item_date) > String(current.item_date) || Number(item.id) > Number(current.id)) {
      map.set(key, item);
    }
  });
  return [...map.values()];
}

function renderPersonalMorningCard(item) {
  const [statusLabel, statusClass] = morningStatusMeta[item.status] || morningStatusMeta.todo;
  const chain = morningChainId(item);
  const color = personalLineColors[hashIndex(chain, personalLineColors.length)];
  const isActive = state.activePersonalMorningChain === chain;
  const viewingAnotherUser = Boolean(
    isAdminView()
    && state.dashboardUserId
    && Number(state.dashboardUserId) !== Number(state.user?.id),
  );
  if (!canOperate("morning", "edit") || viewingAnotherUser) {
    return `<article class="personal-reminder-card ${statusClass} ${isActive ? "calendar-focused" : ""}" data-personal-calendar-focus="${escapeHtml(chain)}" style="--line-color:${color}">
      <div class="personal-card-head"><div><strong>${escapeHtml(item.title)}</strong><div class="personal-card-meta"><span>${escapeHtml(compactDate(item.start_date || item.item_date))} 起 · ${Number(item.duration_days || 1)} 天</span></div></div><span class="pill">${escapeHtml(statusLabel)}</span></div>
      ${item.detail ? `<p>${escapeHtml(item.detail)}</p>` : ""}
      ${item.blocker ? `<p class="risk-text">风险：${escapeHtml(item.blocker)}</p>` : ""}
      <button class="secondary morning-history-btn" type="button" data-morning-history-id="${item.id}">查看进展</button>
    </article>`;
  }
  return `<article class="personal-reminder-card ${statusClass} ${isActive ? "calendar-focused" : ""}" data-personal-calendar-focus="${escapeHtml(chain)}" style="--line-color:${color}">
    <form class="personal-morning-form" data-item-id="${item.id}">
      <input type="hidden" name="expected_version" value="${Number(item.version || 1)}">
      <div class="personal-card-head">
        <div>
          <strong>${escapeHtml(item.title)}</strong>
          <div class="personal-card-meta">
            <span>${escapeHtml(compactDate(item.start_date || item.item_date))} 起 · ${Number(item.duration_days || 1)} 天</span>
            ${item.due_date ? `<span class="${isMorningDue(item) ? "risk-text" : ""}">到期 ${escapeHtml(shortDate(item.due_date))}</span>` : ""}
          </div>
        </div>
        <span class="pill">${escapeHtml(statusLabel)}</span>
      </div>
      <div class="personal-edit-grid">
        <div class="personal-choice-field">
          <span>进度</span>
          ${renderMorningChoiceGroup("status", item.status || "todo", "status")}
        </div>
        <div class="personal-choice-field">
          <span>优先级</span>
          ${renderMorningChoiceGroup("priority", item.priority || "normal", "priority")}
        </div>
        <label>到期<input name="due_date" type="date" value="${escapeHtml(item.due_date || item.item_date)}"></label>
      </div>
      <label class="personal-edit-field">进展 / 下一步<textarea name="detail" placeholder="更新今天的进展、下一步动作">${escapeHtml(item.detail || "")}</textarea></label>
      <label class="personal-edit-field">风险<textarea name="blocker" placeholder="没有风险可留空">${escapeHtml(item.blocker || "")}</textarea></label>
      <div class="personal-card-actions">
        <button type="submit">保存进展</button>
        <button class="secondary morning-history-btn" type="button" data-morning-history-id="${item.id}">查看进展</button>
      </div>
    </form>
  </article>`;
}

function renderPersonalDoneItem(item) {
  const [statusLabel, statusClass] = morningStatusMeta[item.status] || morningStatusMeta.done;
  const chain = morningChainId(item);
  const color = personalLineColors[hashIndex(chain, personalLineColors.length)];
  const isActive = state.activePersonalMorningChain === chain;
  return `<article class="personal-done-item ${statusClass} ${isActive ? "active" : ""}" role="button" tabindex="0" data-personal-calendar-focus="${escapeHtml(chain)}" style="--line-color:${color}">
    <div>
      <strong>${escapeHtml(item.title)}</strong>
      <span>${escapeHtml(compactDate(item.start_date || item.item_date))} 起 · ${Number(item.duration_days || 1)} 天 · ${escapeHtml(statusLabel)}</span>
    </div>
    <button class="secondary morning-history-btn" type="button" data-morning-history-id="${item.id}">进展</button>
  </article>`;
}

function buildPersonalCalendarModel(items = [], month = new Date()) {
  const start = monthStart(month);
  const end = monthEnd(month);
  const chains = new Map();
  items.filter(isMyMorningItem).forEach((item) => {
    if (item.item_date < iso(start) || item.item_date > iso(end)) return;
    const id = morningChainId(item);
    if (!chains.has(id)) {
      chains.set(id, {
        id,
        title: item.title || "事项",
        color: personalLineColors[hashIndex(id, personalLineColors.length)],
        dates: new Map(),
        minDate: item.item_date,
        maxDate: item.item_date,
        lane: 0,
      });
    }
    const chain = chains.get(id);
    const existing = chain.dates.get(item.item_date);
    if (!existing || Number(item.id) >= Number(existing.id)) {
      chain.dates.set(item.item_date, item);
    }
    chain.minDate = String(item.item_date) < String(chain.minDate) ? item.item_date : chain.minDate;
    chain.maxDate = String(item.item_date) > String(chain.maxDate) ? item.item_date : chain.maxDate;
  });
  const laneDates = [];
  const chainList = [...chains.values()].sort((a, b) => String(a.minDate).localeCompare(String(b.minDate)) || String(a.title).localeCompare(String(b.title), "zh-CN"));
  chainList.forEach((chain) => {
    let lane = laneDates.findIndex((dates) => ![...chain.dates.keys()].some((date) => dates.has(date)));
    if (lane < 0) {
      lane = laneDates.length;
      laneDates[lane] = new Set();
    }
    chain.lane = lane;
    chain.dates.forEach((_, date) => laneDates[lane].add(date));
  });
  const byDate = {};
  chainList.forEach((chain) => {
    chain.dates.forEach((item, date) => {
      byDate[date] ||= [];
      byDate[date].push({ chain, item });
    });
  });
  Object.keys(byDate).forEach((date) => {
    byDate[date].sort((a, b) => a.chain.lane - b.chain.lane || String(a.item.title).localeCompare(String(b.item.title), "zh-CN"));
  });
  return { byDate, chains };
}

function renderPersonalMorningCalendar(items = []) {
  const target = $("#personalMorningCalendar");
  if (!target) return;
  const today = new Date();
  const month = new Date(today.getFullYear(), today.getMonth(), 1);
  const start = monthStart(month);
  const gridStart = new Date(start);
  gridStart.setDate(start.getDate() - (start.getDay() || 7) + 1);
  const model = buildPersonalCalendarModel(items, month);
  const weekdays = ["一", "二", "三", "四", "五", "六", "日"].map((day) => `<div class="personal-calendar-weekday">${day}</div>`).join("");
  const cells = [];
  for (let index = 0; index < 42; index += 1) {
    const date = new Date(gridStart);
    date.setDate(gridStart.getDate() + index);
    const dateKey = iso(date);
    const dayEntries = model.byDate[dateKey] || [];
    const hasFocusedLine = dayEntries.some(({ chain }) => chain.id === state.activePersonalMorningChain);
    const visibleLanes = Array.from({ length: 4 }, (_, lane) => dayEntries.find((entry) => entry.chain.lane === lane) || null);
    if (hasFocusedLine && !visibleLanes.some((entry) => entry?.chain.id === state.activePersonalMorningChain)) {
      visibleLanes[3] = dayEntries.find(({ chain }) => chain.id === state.activePersonalMorningChain);
    }
    const visibleChainIds = new Set(visibleLanes.filter(Boolean).map((entry) => entry.chain.id));
    const hiddenCount = dayEntries.filter(({ chain }) => !visibleChainIds.has(chain.id)).length;
    cells.push(`<div class="personal-calendar-day ${date.getMonth() !== month.getMonth() ? "other" : ""} ${dateKey === iso(today) ? "today" : ""} ${hasFocusedLine ? "focused-line-day" : ""}">
      <div class="personal-calendar-date">${date.getDate()}</div>
      <div class="personal-calendar-lines">
        ${visibleLanes.map((entry) => {
          if (!entry) return `<span class="personal-calendar-line-slot"></span>`;
          const { chain, item } = entry;
          const [, statusClass] = morningStatusMeta[item.status] || morningStatusMeta.todo;
          const previousDate = iso(addDays(`${dateKey}T00:00:00`, -1));
          const nextDate = iso(addDays(`${dateKey}T00:00:00`, 1));
          const isWeekStart = date.getDay() === 1;
          const isWeekEnd = date.getDay() === 0;
          const hasPrevious = chain.dates.has(previousDate) && !isWeekStart;
          const hasNext = chain.dates.has(nextDate) && !isWeekEnd;
          const segmentClass = `${hasPrevious ? "connect-left" : "segment-start"} ${hasNext ? "connect-right" : "segment-end"}`;
          const highlighted = chain.id === state.activePersonalMorningChain ? "highlighted" : "";
          const [statusLabel] = morningStatusMeta[item.status] || morningStatusMeta.todo;
          const popoverEdge = date.getDay() === 1 ? "popover-edge-left" : date.getDay() === 0 ? "popover-edge-right" : "";
          return `<span class="personal-calendar-line ${statusClass} ${segmentClass} ${highlighted} ${popoverEdge}" data-chain-id="${escapeHtml(chain.id)}" data-personal-calendar-focus="${escapeHtml(chain.id)}" tabindex="0" style="--line-color:${chain.color}" title="${escapeHtml(item.title)}">
            <span class="personal-line-popover">
              <strong>${escapeHtml(shortDate(dateKey))} · ${escapeHtml(statusLabel)} · ${escapeHtml(morningPriorityMeta[item.priority] || "中")}</strong>
              <b>${escapeHtml(item.title)}</b>
              ${item.detail ? `<small>进展：${escapeHtml(item.detail)}</small>` : ""}
              ${item.blocker ? `<small class="risk-text">风险：${escapeHtml(item.blocker)}</small>` : ""}
            </span>
          </span>`;
        }).join("")}
        ${hiddenCount ? `<span class="personal-calendar-more">+${hiddenCount}</span>` : ""}
      </div>
      ${dayEntries.length ? `<div class="personal-calendar-popover">
        <strong>${escapeHtml(shortDate(dateKey))}</strong>
        ${dayEntries.map(({ chain, item }) => {
          const [statusLabel] = morningStatusMeta[item.status] || morningStatusMeta.todo;
          const highlighted = chain.id === state.activePersonalMorningChain ? "active" : "";
          return `<div class="personal-calendar-popover-item ${highlighted}" role="button" tabindex="0" data-personal-calendar-focus="${escapeHtml(chain.id)}" style="--line-color:${chain.color}">
            <span>${escapeHtml(statusLabel)} · ${escapeHtml(morningPriorityMeta[item.priority] || "中")}</span>
            <b>${escapeHtml(item.title)}</b>
            ${item.detail ? `<small>进展：${escapeHtml(item.detail)}</small>` : ""}
            ${item.blocker ? `<small class="risk-text">风险：${escapeHtml(item.blocker)}</small>` : ""}
          </div>`;
        }).join("")}
      </div>` : ""}
    </div>`);
  }
  target.innerHTML = weekdays + cells.join("");
}

function renderPersonalMorningList(items = [], monthItems = items) {
  const activeTarget = $("#personalMorningActiveList");
  const doneTarget = $("#personalMorningDoneList");
  if (!activeTarget || !doneTarget) return;
  const myItems = sortMorningForWorkbench(items.filter(isMyMorningItem));
  const activeItems = myItems.filter((item) => item.status !== "done");
  const doneItems = latestByMorningChain(monthItems.filter((item) => isMyMorningItem(item) && item.status === "done"))
    .sort((a, b) => String(b.item_date).localeCompare(String(a.item_date)) || String(a.title || "").localeCompare(String(b.title || ""), "zh-CN"));
  activeTarget.innerHTML = activeItems.length
    ? activeItems.map(renderPersonalMorningCard).join("")
    : `<p class="empty-note">今天没有进行中的早例会事项。</p>`;
  doneTarget.innerHTML = doneItems.length
    ? doneItems.map(renderPersonalDoneItem).join("")
    : `<p class="empty-note">本月还没有完成事项。</p>`;
  renderPersonalMorningCalendar(monthItems);
}

function renderPersonalWorkbench({ morningItems = [], monthItems = [] } = {}) {
  if (!$("#personalMorningActiveList")) return;
  state.personalMorningMonthItems = monthItems.length ? monthItems : morningItems;
  const chainExists = state.personalMorningMonthItems.some((item) => morningChainId(item) === state.activePersonalMorningChain);
  if (!chainExists) state.activePersonalMorningChain = null;
  renderPersonalMorningList(morningItems, state.personalMorningMonthItems);
}

function focusPersonalMorningChain(chain) {
  state.activePersonalMorningChain = chain || null;
  renderPersonalMorningCalendar(state.personalMorningMonthItems);
  $$("[data-personal-calendar-focus]").forEach((item) => {
    const isActive = item.dataset.personalCalendarFocus === state.activePersonalMorningChain;
    item.classList.toggle("calendar-focused", isActive);
    if (item.classList.contains("personal-done-item")) {
      item.classList.toggle("active", isActive);
    }
  });
  $("#personalMorningCalendar")?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function findMyDashboardRow(items = []) {
  return items.find((item) => Number(item.id) === Number(state.dashboardUserId || state.user?.id)) || null;
}

function renderOwnScoreSummary(score) {
  if (!score) return `<p class="empty-note">当前周期暂无你的红黑榜积分。</p>`;
  return `
    <div class="rank-row"><span class="rank-no">红</span><strong>红榜加分</strong><span>${Number(score.red_points || 0)} 分</span></div>
    <div class="rank-row"><span class="rank-no">黑</span><strong>黑榜记录</strong><span>${Number(score.black_points || 0)} 分</span></div>
  `;
}

function renderOwnThanksSummary(thanks) {
  if (!thanks) return `<p class="empty-note">当前周期暂无你收到的 Thank You。</p>`;
  return `
    <div class="rank-row"><span class="rank-no">谢</span><strong>收到感谢</strong><span>${Number(thanks.thanks || 0)} 次</span></div>
  `;
}

async function loadPersonalMorningMonth(userId = null) {
  const today = iso(new Date());
  const start = iso(monthStart(new Date()));
  const dates = dateListBetween(start, today);
  const userQuery = userId ? `&user_id=${encodeURIComponent(userId)}` : "";
  const responses = await Promise.all(dates.map((date) => api(`/api/morning-items?date=${encodeURIComponent(date)}${userQuery}`)));
  const todayData = responses.find((response) => response.date === today) || responses[responses.length - 1] || { items: [] };
  return {
    today: todayData,
    monthItems: responses.flatMap((response) => response.items || []),
  };
}

async function loadDashboard() {
  const emptyScores = { totals: [], timeline: [] };
  const emptyThanks = { stars: [] };
  const emptyShifts = { by_user: [], by_machine: [] };
  const emptyMorning = { today: { items: [] }, monthItems: [] };
  if (isAdminView()) {
    const response = await api("/api/users/coordination").catch(() => ({ users: [] }));
    state.dashboardUsers = response.users || [];
  } else {
    state.dashboardUsers = state.user ? [state.user] : [];
    state.dashboardUserId = state.user?.id || null;
  }
  if (!state.dashboardUsers.some((user) => Number(user.id) === Number(state.dashboardUserId))) {
    state.dashboardUserId = state.dashboardUsers.find((user) => Number(user.id) === Number(state.user?.id))?.id
      || state.dashboardUsers[0]?.id
      || state.user?.id
      || null;
  }
  const selectedUser = state.dashboardUsers.find((user) => Number(user.id) === Number(state.dashboardUserId));
  const metricOwner = selectedUser?.display_name || "我";
  const targetQuery = isAdminView() && state.dashboardUserId ? `&user_id=${encodeURIComponent(state.dashboardUserId)}` : "";
  const [scores, thanks, shifts, morning] = await Promise.all([
    canLoadModule("rules") ? api(`/api/dashboards/red-black?${periodQuery()}${targetQuery}`).catch(() => emptyScores) : emptyScores,
    canLoadModule("thanks") ? api(`/api/dashboards/thank-you?${periodQuery()}${targetQuery}`).catch(() => emptyThanks) : emptyThanks,
    canLoadModule("shifts") ? api(`/api/dashboards/shifts?${periodQuery()}${targetQuery}`).catch(() => emptyShifts) : emptyShifts,
    canLoadModule("morning") ? loadPersonalMorningMonth(isAdminView() ? state.dashboardUserId : null).catch(() => emptyMorning) : emptyMorning,
  ]);
  const myScore = findMyDashboardRow(scores.totals);
  const myThanks = findMyDashboardRow(thanks.stars);
  const myShift = findMyDashboardRow(shifts.by_user);
  const myMorningItems = (morning.today?.items || []).filter(isMyMorningItem);
  $("#metricScore").textContent = `红 ${Number(myScore?.red_points || 0)} / 黑 ${Number(myScore?.black_points || 0)}`;
  $("#metricThanks").textContent = Number(myThanks?.thanks || 0);
  $("#metricHours").textContent = Number(myShift?.hours || 0);
  $("#metricMeetings").textContent = myMorningItems.length;
  if ($("#metricScoreLabel")) $("#metricScoreLabel").textContent = `${metricOwner}的红榜 / 黑榜积分`;
  if ($("#metricThanksLabel")) $("#metricThanksLabel").textContent = `${metricOwner}收到的 Thank You`;
  if ($("#metricHoursLabel")) $("#metricHoursLabel").textContent = `${metricOwner}的已排工时`;
  if ($("#metricMeetingsLabel")) $("#metricMeetingsLabel").textContent = `${metricOwner}的早例会事项`;
  $("#scoreRank").innerHTML = renderOwnScoreSummary(myScore);
  $("#thanksRank").innerHTML = renderOwnThanksSummary(myThanks);
  const viewingOther = Boolean(isAdminView() && selectedUser && Number(selectedUser.id) !== Number(state.user?.id));
  const dashboardField = $("#dashboardUserField");
  dashboardField?.classList.toggle("hidden", !isAdminView());
  const dashboardSelect = $("#dashboardUserSelect");
  if (dashboardSelect) {
    dashboardSelect.innerHTML = state.dashboardUsers.map((user) => {
      const label = user.org_unit_name ? `${user.display_name} · ${user.org_unit_name}` : user.display_name;
      return `<option value="${user.id}" ${Number(user.id) === Number(state.dashboardUserId) ? "selected" : ""}>${escapeHtml(label)}</option>`;
    }).join("");
  }
  if ($("#personalWorkbenchTitle")) {
    $("#personalWorkbenchTitle").textContent = viewingOther ? `${selectedUser.display_name}的工作台` : "我的工作台";
  }
  $("#personalMorningCreateForm")?.classList.toggle("hidden", viewingOther);
  renderPersonalWorkbench({
    morningItems: morning.today?.items || [],
    monthItems: morning.monthItems || [],
  });
}

const morningStatusMeta = {
  todo: ["待处理", "status-todo"],
  doing: ["进行中", "status-doing"],
  risk: ["有风险", "status-risk"],
  done: ["已完成", "status-done"],
};

const morningPriorityMeta = {
  low: "低",
  normal: "中",
  high: "高",
};

const morningStatusChoices = [
  ["todo", "待处理"],
  ["doing", "进行中"],
  ["risk", "有风险"],
  ["done", "已完成"],
];

const morningPriorityChoices = [
  ["high", "高"],
  ["normal", "中"],
  ["low", "低"],
];

const meetingItemStatusMeta = {
  todo: ["待处理", "status-todo"],
  doing: ["进行中", "status-doing"],
  done: ["已完成", "status-done"],
};

const meetingStatusMeta = {
  draft: ["草稿", "会前整理", "status-draft"],
  scheduled: ["待召开", "准备材料", "status-scheduled"],
  in_progress: ["进行中", "聚焦讨论", "status-in-progress"],
  completed: ["已结束", "纪要锁定", "status-completed"],
  archived: ["已归档", "只读保存", "status-archived"],
};

function normalizedMeetingStatus(status) {
  return meetingStatusMeta[status] ? status : "scheduled";
}

function meetingIsLocked(meeting) {
  return ["completed", "archived"].includes(normalizedMeetingStatus(meeting?.status));
}

function renderMorningStatusOptions(selected) {
  return Object.entries(morningStatusMeta)
    .map(([value, meta]) => `<option value="${value}" ${value === selected ? "selected" : ""}>${meta[0]}</option>`)
    .join("");
}

function renderMorningPriorityOptions(selected) {
  return Object.entries(morningPriorityMeta)
    .map(([value, label]) => `<option value="${value}" ${value === selected ? "selected" : ""}>${label}</option>`)
    .join("");
}

function renderMorningChoiceGroup(name, selected, kind) {
  const choices = kind === "priority" ? morningPriorityChoices : morningStatusChoices;
  const fallback = kind === "priority" ? "normal" : "todo";
  const value = choices.some(([choiceValue]) => choiceValue === selected) ? selected : fallback;
  return `
    <input name="${escapeHtml(name)}" type="hidden" value="${escapeHtml(value)}" />
    <div class="morning-choice-group ${escapeHtml(kind)}" role="group" aria-label="${kind === "priority" ? "事项优先级" : "事项进度"}">
      ${choices.map(([choiceValue, label]) => `
        <button class="morning-choice-btn ${escapeHtml(kind)}-${escapeHtml(choiceValue)} ${choiceValue === value ? "active" : ""}" type="button" data-choice-name="${escapeHtml(name)}" data-choice-value="${escapeHtml(choiceValue)}">
          ${escapeHtml(label)}
        </button>`).join("")}
    </div>`;
}

function syncMorningChoiceGroups(root = document) {
  $$(".morning-choice-group", root).forEach((group) => {
    const firstButton = group.querySelector("[data-choice-name]");
    const name = firstButton?.dataset.choiceName;
    const input = name ? group.closest("form")?.elements[name] : null;
    if (!input) return;
    $$(".morning-choice-btn", group).forEach((button) => {
      button.classList.toggle("active", button.dataset.choiceValue === input.value);
    });
  });
}

function setMorningChoice(button) {
  const form = button.closest("form");
  const group = button.closest(".morning-choice-group");
  const name = button.dataset.choiceName;
  if (!form || !group || !name || !form.elements[name]) return;
  form.elements[name].value = button.dataset.choiceValue || "";
  $$(".morning-choice-btn", group).forEach((item) => {
    item.classList.toggle("active", item === button);
  });
  if (name === "status" && button.dataset.choiceValue === "risk") {
    form.elements.blocker?.focus();
  }
}

function renderMeetingItemStatusOptions(selected) {
  return Object.entries(meetingItemStatusMeta)
    .map(([value, meta]) => `<option value="${value}" ${value === selected ? "selected" : ""}>${meta[0]}</option>`)
    .join("");
}

function isMorningDue(item) {
  return item.status !== "done" && item.due_date && item.due_date <= state.morningDate;
}

function morningRiskItems(items = state.morningItems) {
  return items
    .filter((item) => item.status === "risk" || item.blocker || item.priority === "high" || isMorningDue(item))
    .sort((a, b) => {
      const score = (item) => (item.status === "risk" ? 4 : 0) + (item.blocker ? 3 : 0) + (isMorningDue(item) ? 2 : 0) + (item.priority === "high" ? 1 : 0);
      return score(b) - score(a);
    });
}

function renderMorningFocus() {
  const target = $("#morningFocusList");
  if (!target) return;
  const risks = morningRiskItems().slice(0, 4);
  target.innerHTML = risks.length
    ? `<strong>今日风险重点</strong>${risks.map((item) => `
        <span class="morning-focus-chip ${item.status === "risk" ? "is-risk" : ""}">
          ${escapeHtml(item.owner_name || "未分配")} · ${escapeHtml(item.title)}
          ${item.blocker ? `｜风险：${escapeHtml(item.blocker)}` : ""}
        </span>
      `).join("")}`
    : `<strong>今日风险重点</strong><span class="morning-focus-chip">暂无明确风险，按清单推进即可</span>`;
}

function renderMorningSummary() {
  const totals = { todo: 0, doing: 0, risk: 0, done: 0 };
  state.morningItems.forEach((item) => { totals[item.status] = (totals[item.status] || 0) + 1; });
  const total = state.morningItems.length;
  const activeTotal = state.morningItems.filter((item) => item.status !== "done").length;
  const dueTotal = state.morningItems.filter(isMorningDue).length;
  $("#morningStats").innerHTML = `
    <div class="morning-stat status-total">
      <span>总事项</span>
      <strong>${total}</strong>
    </div>
    <div class="morning-stat status-active">
      <span>未完成</span>
      <strong>${activeTotal}</strong>
    </div>
    <div class="morning-stat status-risk">
      <span>风险</span>
      <strong>${totals.risk || 0}</strong>
    </div>
    <div class="morning-stat status-due">
      <span>到期/逾期</span>
      <strong>${dueTotal}</strong>
    </div>
    <div class="morning-stat status-carried">
      <span>自动带入</span>
      <strong>${state.morningCarriedCount || 0}</strong>
    </div>`;
  renderMorningFocus();
}

function renderMorningBoard() {
  const board = $("#morningBoard");
  if (!board) return;
  const users = state.morningUsers;
  if (!users.length) {
    board.innerHTML = "<p>暂无成员数据</p>";
    return;
  }
  let ownerFilter = $("#morningOwnerFilter")?.value || "";
  const statusFilter = $("#morningStatusFilter")?.value || "";
  const ownerOptions = `<option value="">全部成员</option>${users.map((user) => `<option value="${user.id}">${escapeHtml(user.display_name)}</option>`).join("")}`;
  const ownerSelect = $("#morningOwnerFilter");
  if (ownerSelect) {
    const current = ownerSelect.value;
    ownerSelect.innerHTML = ownerOptions;
    ownerSelect.value = users.some((user) => String(user.id) === String(current)) ? current : "";
    ownerFilter = ownerSelect.value;
  }
  const byOwner = {};
  const filteredItems = state.morningItems.filter((item) => {
    if (ownerFilter && String(item.owner_id) !== String(ownerFilter)) return false;
    if (statusFilter && item.status !== statusFilter) return false;
    return true;
  });
  filteredItems.forEach((item) => {
    byOwner[item.owner_id] = byOwner[item.owner_id] || [];
    byOwner[item.owner_id].push(item);
  });
  const visibleUsers = users.filter((user) => !ownerFilter || String(user.id) === String(ownerFilter));
  board.innerHTML = visibleUsers.map((user) => {
    const items = byOwner[user.id] || [];
    const personSummary = {
      active: items.filter((item) => item.status !== "done").length,
      risk: items.filter((item) => item.status === "risk" || item.blocker).length,
      done: items.filter((item) => item.status === "done").length,
    };
    return `
      <section class="morning-person-row" id="morning-owner-${user.id}" data-morning-owner-id="${user.id}">
        <div class="morning-person-head">
          <div>
            <strong>${escapeHtml(user.display_name)}</strong>
            <span>账号 ${escapeHtml(user.username || "")}</span>
          </div>
          <div class="morning-person-summary">
            <span>全部 ${items.length}</span>
            <span>未完成 ${personSummary.active}</span>
            <span class="${personSummary.risk ? "is-risk" : ""}">风险 ${personSummary.risk}</span>
            <span>完成 ${personSummary.done}</span>
          </div>
        </div>
        <div class="morning-list-head">
          <span>状态</span>
          <span>事项点</span>
          <span>今日进展 / 下一步</span>
          <span>风险 / 到期</span>
          <span>操作</span>
        </div>
        <div class="morning-item-stack">
          ${items.length ? items.map(renderMorningItem).join("") : `<p class="empty-note">当天暂无匹配事项</p>`}
        </div>
      </section>
    `;
  }).join("");
}

function renderMorningNavigator() {
  const list = $("#morningNavigatorList");
  if (!list) return;
  const ownerFilter = $("#morningOwnerFilter")?.value || "";
  const users = state.morningUsers;
  const counts = new Map();
  state.morningItems.forEach((item) => counts.set(Number(item.owner_id), (counts.get(Number(item.owner_id)) || 0) + 1));
  list.innerHTML = users.map((user, index) => `
    <div class="morning-navigator-item ${ownerFilter && String(user.id) !== String(ownerFilter) ? "is-filtered" : ""} ${ownerFilter && String(user.id) === String(ownerFilter) ? "is-current" : ""}"
         draggable="${isAdminView()}" data-morning-nav-user-id="${user.id}">
      ${isAdminView() ? `<span class="morning-nav-drag" title="拖动调整顺序" aria-hidden="true">⋮⋮</span>` : ""}
      <button class="morning-nav-jump" type="button" data-morning-owner-target="${user.id}">
        <span>${escapeHtml(user.display_name)}</span><small>${counts.get(Number(user.id)) || 0}</small>
      </button>
      ${isAdminView() ? `<span class="morning-nav-order-actions">
        <button type="button" data-morning-order-user="${user.id}" data-morning-order-direction="up" title="上移" aria-label="上移 ${escapeHtml(user.display_name)}" ${index === 0 ? "disabled" : ""}>↑</button>
        <button type="button" data-morning-order-user="${user.id}" data-morning-order-direction="down" title="下移" aria-label="下移 ${escapeHtml(user.display_name)}" ${index === users.length - 1 ? "disabled" : ""}>↓</button>
      </span>` : ""}
    </div>
  `).join("") || `<p class="empty-note">暂无早例会成员</p>`;
  const syncState = $("#morningSyncState");
  if (syncState) {
    syncState.textContent = state.morningUpdatePending ? "有新内容，点击刷新" : "自动同步中";
    syncState.classList.toggle("has-update", state.morningUpdatePending);
  }
}

function morningEditorIsActive() {
  const active = document.activeElement;
  return Boolean(active?.closest?.("#morningCreatePanel, .morning-item-form"));
}

async function saveMorningOrder(userIds) {
  const data = await api("/api/morning-items/order", {
    method: "PATCH",
    body: JSON.stringify({ user_ids: userIds, date: state.morningDate }),
  });
  state.morningItems = data.items || state.morningItems;
  state.morningUsers = data.users || state.morningUsers;
  state.morningVersionToken = data.version_token || state.morningVersionToken;
  state.morningUpdatePending = false;
  renderMorning();
}

async function moveMorningUser(userId, direction) {
  const ids = state.morningUsers.map((user) => Number(user.id));
  const index = ids.indexOf(Number(userId));
  const target = direction === "up" ? index - 1 : index + 1;
  if (index < 0 || target < 0 || target >= ids.length) return;
  [ids[index], ids[target]] = [ids[target], ids[index]];
  await saveMorningOrder(ids);
}

async function checkMorningUpdates() {
  if (state.currentPage !== "morning" || document.visibilityState !== "visible" || state.morningLoading || !canLoadModule("morning")) return;
  try {
    const data = await api(`/api/morning-items/version?date=${encodeURIComponent(state.morningDate)}`);
    const token = data.version_token || "";
    if (!state.morningVersionToken) {
      state.morningVersionToken = token;
      return;
    }
    if (token === state.morningVersionToken) return;
    if (morningEditorIsActive()) {
      state.morningUpdatePending = true;
      renderMorningNavigator();
      return;
    }
    await loadMorning({ preserveScroll: true });
  } catch {
    // A transient polling failure should not interrupt the current meeting view.
  }
}

function startMorningPolling() {
  window.setInterval(checkMorningUpdates, 12000);
}

function canEditMorningItem(item) {
  return canOperate("morning", "edit")
    && !state.morningReadOnly
    && !item.retained_from_previous_workday
    && (isAdminView() || Number(item.owner_id) === Number(state.user?.id));
}

function renderMorningItem(item) {
  const [statusLabel, statusClass] = morningStatusMeta[item.status] || morningStatusMeta.todo;
  const canEdit = canEditMorningItem(item);
  const durationText = item.retained_from_previous_workday
    ? `上个工作日完成 · ${compactDate(item.retained_from_date || item.item_date)}`
    : `${compactDate(item.start_date || item.item_date)}起 · ${Number(item.duration_days || 1)}天`;
  const dueText = item.due_date ? `${isMorningDue(item) ? "到期需处理" : "到期"} ${shortDate(item.due_date)}` : "未设到期";
  const riskText = item.blocker ? item.blocker : (item.status === "risk" ? "请补充风险说明" : "暂无风险");
  return `
    <article class="morning-item-card morning-list-item ${statusClass}" data-morning-history-id="${item.id}">
      ${canEdit ? `
        <form class="morning-item-form morning-list-item-form" data-item-id="${item.id}">
          <input type="hidden" name="expected_version" value="${Number(item.version || 1)}">
          <div class="morning-status-cell">
            <div class="morning-badge-stack">
              <span class="morning-badge ${statusClass}">${escapeHtml(statusLabel)}</span>
              <span class="morning-badge priority-${escapeHtml(item.priority || "normal")}">优先级 ${escapeHtml(morningPriorityMeta[item.priority] || "中")}</span>
              <span class="morning-badge source">${escapeHtml(durationText)}</span>
            </div>
            <select name="status">${renderMorningStatusOptions(item.status)}</select>
            <select name="priority">${renderMorningPriorityOptions(item.priority)}</select>
          </div>
          <input class="morning-title-cell" name="title" value="${escapeHtml(item.title)}" placeholder="事项点" required>
          <textarea class="morning-detail-cell" name="detail" placeholder="今日进展 / 下一步">${escapeHtml(item.detail || "")}</textarea>
          <div class="morning-risk-cell">
            <input name="blocker" value="${escapeHtml(item.blocker || "")}" placeholder="风险说明">
            <input name="due_date" type="date" value="${escapeHtml(item.due_date || item.item_date)}">
            <small class="${isMorningDue(item) ? "risk-text" : ""}">${escapeHtml(dueText)}</small>
          </div>
          <div class="morning-item-actions">
            <button type="submit">保存</button>
            <button class="secondary morning-history-btn" type="button" data-morning-history-id="${item.id}">进展</button>
            ${canOperate("morning", "delete") ? `<button class="danger morning-delete-btn" type="button" data-item-id="${item.id}" data-item-version="${Number(item.version || 1)}">删除</button>` : ""}
          </div>
        </form>
      ` : `
        <div class="morning-status-cell">
          <div class="morning-badge-stack">
            <span class="morning-badge ${statusClass}">${escapeHtml(statusLabel)}</span>
            <span class="morning-badge priority-${escapeHtml(item.priority || "normal")}">优先级 ${escapeHtml(morningPriorityMeta[item.priority] || "中")}</span>
            <span class="morning-badge source">${escapeHtml(durationText)}</span>
          </div>
        </div>
        <div class="morning-title-cell">
          <strong>${escapeHtml(item.title)}</strong>
          <small>更新 ${escapeHtml(shortDateTime(item.updated_at || item.created_at))}</small>
        </div>
        <p class="morning-detail-cell">${escapeHtml(item.detail || "暂无进展说明")}</p>
        <div class="morning-risk-cell">
          <p class="${item.blocker || item.status === "risk" ? "risk-text" : ""}">风险：${escapeHtml(riskText)}</p>
          <small class="${isMorningDue(item) ? "risk-text" : ""}">${escapeHtml(dueText)}</small>
        </div>
        <div class="morning-item-actions">
          <button class="secondary morning-history-btn" type="button" data-morning-history-id="${item.id}">进展</button>
          <span class="pill">${item.retained_from_previous_workday ? "昨日完成回顾" : state.morningReadOnly ? "历史只读" : "只读"}</span>
        </div>
      `}
    </article>
  `;
}

function closeMorningHistoryModal() {
  const modal = $("#morningHistoryModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

function renderMorningHistory(data) {
  const item = data.item || {};
  const history = data.history || [];
  const [statusLabel, statusClass] = morningStatusMeta[item.status] || morningStatusMeta.todo;
  const title = $("#morningHistoryTitle");
  const subtitle = $("#morningHistorySubtitle");
  const meta = $("#morningHistoryMeta");
  const list = $("#morningHistoryList");
  if (title) title.textContent = item.title || "事项进展";
  if (subtitle) {
    subtitle.textContent = `${item.owner_name || "负责人"} · 从 ${shortDate(item.start_date || item.item_date)} 开始 · 持续 ${Number(item.duration_days || 1)} 天`;
  }
  if (meta) {
    meta.innerHTML = `
      <span class="morning-badge ${statusClass}">${escapeHtml(statusLabel)}</span>
      <span class="morning-badge priority-${escapeHtml(item.priority || "normal")}">优先级 ${escapeHtml(morningPriorityMeta[item.priority] || "中")}</span>
      <span class="morning-badge source">开始 ${escapeHtml(shortDate(item.start_date || item.item_date))}</span>
      <span class="morning-badge source">持续 ${Number(item.duration_days || 1)} 天</span>
    `;
  }
  if (!list) return;
  if (!history.length) {
    list.innerHTML = `<p class="empty-note">这条事项还没有手动更新记录。自动带入但未更新的日期不会展示。</p>`;
    return;
  }
  list.innerHTML = history.map((row) => {
    const [rowStatusLabel, rowStatusClass] = morningStatusMeta[row.status] || morningStatusMeta.todo;
    return `
      <article class="morning-history-entry ${rowStatusClass}">
        <div class="morning-history-date">
          <strong>${escapeHtml(shortDate(row.item_date))}</strong>
          <span>${escapeHtml(row.updated_by_name || row.owner_name || "成员")} 更新于 ${escapeHtml(shortDateTime(row.updated_at || row.created_at))}</span>
        </div>
        <div class="morning-history-content">
          <span class="morning-badge ${rowStatusClass}">${escapeHtml(rowStatusLabel)}</span>
          <h3>${escapeHtml(row.title || item.title || "事项")}</h3>
          <p>${escapeHtml(row.detail || "暂无进展说明")}</p>
          ${row.blocker ? `<p class="risk-text">风险：${escapeHtml(row.blocker)}</p>` : ""}
          <small>到期 ${escapeHtml(shortDate(row.due_date || row.item_date))} · 持续第 ${Number(row.duration_days || 1)} 天</small>
        </div>
      </article>
    `;
  }).join("");
}

async function openMorningHistory(itemId) {
  const modal = $("#morningHistoryModal");
  if (!modal || !itemId) return;
  $("#morningHistoryTitle").textContent = "事项进展";
  $("#morningHistorySubtitle").textContent = "正在加载...";
  $("#morningHistoryMeta").innerHTML = "";
  $("#morningHistoryList").innerHTML = `<p class="empty-note">正在加载进展记录...</p>`;
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  const data = await api(`/api/morning-items/${itemId}/history`);
  renderMorningHistory(data);
}

function renderMorning() {
  const dateInput = $("#morningDate");
  if (dateInput) dateInput.value = state.morningDate;
  if (isAdminView()) {
    $("#morningOwnerField")?.classList.remove("hidden");
  } else {
    $("#morningOwnerField")?.classList.add("hidden");
  }
  const createPanel = $("#morningCreatePanel");
  if (createPanel) createPanel.classList.toggle("hidden", state.morningReadOnly);
  const hint = $("#morningLockHint");
  if (hint) {
    hint.classList.toggle("hidden", false);
    hint.textContent = state.morningReadOnly
      ? "当前日期已结束，早例会记录已锁定，只能查看不能修改。"
      : state.morningCarriedCount > 0
        ? `已自动带入 ${state.morningCarriedCount} 条未完成事项。`
        : "未完成事项会持续跟踪，进入新一天时自动带入。";
  }
  renderMorningSummary();
  renderMorningBoard();
  renderMorningNavigator();
  populateSelects();
}

async function loadMorning(options = {}) {
  if (!canLoadModule("morning")) return;
  const loadId = ++state.morningLoadId;
  const organizationPath = selectedOrganizationPath();
  const scrollTop = options.preserveScroll ? window.scrollY : null;
  state.morningLoading = true;
  const date = $("#morningDate")?.value || state.morningDate || iso(new Date());
  state.morningDate = date;
  try {
    const data = await api(`/api/morning-items?date=${encodeURIComponent(date)}`);
    if (loadId !== state.morningLoadId || organizationPath !== selectedOrganizationPath()) return;
    state.morningItems = data.items;
    state.morningUsers = data.users;
    state.morningReadOnly = Boolean(data.read_only);
    state.morningCarriedCount = Number(data.carried_count || 0);
    state.morningVersionToken = data.version_token || "";
    state.morningUpdatePending = false;
    renderMorning();
    if (scrollTop !== null) requestAnimationFrame(() => window.scrollTo({ top: scrollTop }));
  } finally {
    if (loadId === state.morningLoadId) state.morningLoading = false;
  }
}

let processTemplateKeySequence = 0;

function nextProcessTemplateKey() {
  processTemplateKeySequence += 1;
  return `step-${Date.now()}-${processTemplateKeySequence}`;
}

function processTemplateItemEditor(item = {}, index = 0) {
  const itemKey = item._key || nextProcessTemplateKey();
  return `
    <div class="process-template-item-editor ${state.selectedProcessTemplateItemKey === itemKey ? "is-selected" : ""}" data-process-template-item data-process-item-key="${escapeHtml(itemKey)}" data-process-parent-key="${escapeHtml(item._parentKey || "")}">
      <span class="process-template-item-order">${index + 1}</span>
      <div class="process-template-item-fields">
        <input data-process-item-title maxlength="120" value="${escapeHtml(item.title || "")}" placeholder="步骤标题，例如：确认输入资料齐全" />
        <input data-process-item-description maxlength="500" value="${escapeHtml(item.description || "")}" placeholder="补充完成标准或注意事项（可选）" />
      </div>
      <label class="process-parent-field">
        <span>上一步</span>
        <select data-process-item-parent aria-label="上一步"></select>
      </label>
      <label class="process-required-toggle"><input data-process-item-required type="checkbox" ${item.required === false ? "" : "checked"} /><span>必做</span></label>
      <div class="process-template-item-actions">
        <button class="icon-button" type="button" data-process-item-move="-1" title="上移" aria-label="上移">↑</button>
        <button class="icon-button" type="button" data-process-item-move="1" title="下移" aria-label="下移">↓</button>
        <button class="icon-button danger" type="button" data-process-item-remove title="删除 Checklist" aria-label="删除 Checklist">×</button>
      </div>
    </div>
  `;
}

function processTemplateEditorItems() {
  return $$("#processTemplateItems [data-process-template-item]").map((row, index) => ({
    key: row.dataset.processItemKey || "",
    parentKey: $("[data-process-item-parent]", row)?.value || row.dataset.processParentKey || "",
    title: $("[data-process-item-title]", row)?.value.trim() || `步骤 ${index + 1}`,
    required: Boolean($("[data-process-item-required]", row)?.checked),
    order: index + 1,
  }));
}

function renderProcessTemplateMindmap() {
  const target = $("#processTemplateMindmap");
  if (!target) return;
  const items = processTemplateEditorItems();
  if (!items.length) {
    target.innerHTML = '<div class="process-flow-empty">请添加流程节点</div>';
    return;
  }
  const byKey = new Map(items.map((item) => [item.key, item]));
  const children = new Map();
  items.forEach((item) => {
    if (!item.parentKey || !byKey.has(item.parentKey)) return;
    if (!children.has(item.parentKey)) children.set(item.parentKey, []);
    children.get(item.parentKey).push(item);
  });
  const roots = items.filter((item) => !item.parentKey || !byKey.has(item.parentKey));
  const renderNode = (item, trail = new Set()) => {
    if (trail.has(item.key)) return "";
    const nextTrail = new Set(trail);
    nextTrail.add(item.key);
    const descendants = children.get(item.key) || [];
    return `
      <li>
        <button
          class="process-mindmap-node ${state.selectedProcessTemplateItemKey === item.key ? "is-selected" : ""}"
          type="button"
          data-process-mindmap-select="${escapeHtml(item.key)}"
          title="点击编辑 ${escapeHtml(item.title)}"
        >
          <span>${item.order}</span>
          <strong>${escapeHtml(item.title)}</strong>
          <small>${item.required ? "必做" : "可选"}</small>
        </button>
        ${descendants.length ? `<ul>${descendants.map((child) => renderNode(child, nextTrail)).join("")}</ul>` : ""}
      </li>`;
  };
  target.innerHTML = `
    <div class="process-flow-scroll process-mindmap-scroll">
      <div class="process-flow-tree process-mindmap-tree">
        <ul>${roots.map((root) => renderNode(root)).join("")}</ul>
      </div>
    </div>`;
}

function selectProcessTemplateItem(itemKey, focusTitle = false) {
  const rows = $$("#processTemplateItems [data-process-template-item]");
  const selected = rows.find((row) => row.dataset.processItemKey === itemKey) || rows[0];
  state.selectedProcessTemplateItemKey = selected?.dataset.processItemKey || null;
  rows.forEach((row) => row.classList.toggle("is-selected", row === selected));
  const hint = $("#processSelectedItemHint");
  if (hint && selected) {
    const title = $("[data-process-item-title]", selected)?.value.trim() || "未命名节点";
    hint.textContent = `正在编辑：${title}`;
  }
  const addChild = $("#addProcessTemplateItemBtn");
  if (addChild) addChild.disabled = !selected;
  renderProcessTemplateMindmap();
  if (focusTitle) $("[data-process-item-title]", selected)?.focus();
}

function appendProcessTemplateItem(parentKey = "") {
  const target = $("#processTemplateItems");
  if (!target) return;
  const itemKey = nextProcessTemplateKey();
  target.insertAdjacentHTML(
    "beforeend",
    processTemplateItemEditor(
      {
        _key: itemKey,
        _parentKey: parentKey,
      },
      target.children.length,
    ),
  );
  state.selectedProcessTemplateItemKey = itemKey;
  refreshProcessTemplateItemOrder();
  selectProcessTemplateItem(itemKey, true);
}

function refreshProcessTemplateItemOrder() {
  const rows = $$("#processTemplateItems [data-process-template-item]");
  rows.forEach((row, index) => {
    const order = $(".process-template-item-order", row);
    if (order) order.textContent = index + 1;
    const select = $("[data-process-item-parent]", row);
    if (!select) return;
    const currentParent = select.value || row.dataset.processParentKey || "";
    const options = rows.slice(0, index).map((candidate, candidateIndex) => {
      const key = candidate.dataset.processItemKey || "";
      const title = $("[data-process-item-title]", candidate)?.value.trim() || `步骤 ${candidateIndex + 1}`;
      return `<option value="${escapeHtml(key)}">${candidateIndex + 1}. ${escapeHtml(title)}</option>`;
    });
    select.innerHTML = `<option value="">并行起点</option>${options.join("")}`;
    const validParent = rows.slice(0, index).some((candidate) => candidate.dataset.processItemKey === currentParent);
    select.value = validParent ? currentParent : "";
    row.dataset.processParentKey = select.value;
    const requiredInput = $("[data-process-item-required]", row);
    const parentRow = rows.slice(0, index).find((candidate) => candidate.dataset.processItemKey === select.value);
    const parentOptional = Boolean(parentRow && !$("[data-process-item-required]", parentRow)?.checked);
    if (requiredInput) {
      if (parentOptional) requiredInput.checked = false;
      requiredInput.disabled = parentOptional;
      requiredInput.title = parentOptional ? "上一步为可选节点，本节点也必须是可选" : "";
    }
  });
  if (!rows.some((row) => row.dataset.processItemKey === state.selectedProcessTemplateItemKey)) {
    state.selectedProcessTemplateItemKey = rows[0]?.dataset.processItemKey || null;
  }
  selectProcessTemplateItem(state.selectedProcessTemplateItemKey);
}

function closeProcessTemplateModal() {
  $("#processTemplateModal")?.classList.add("hidden");
  $("#processTemplateModal")?.setAttribute("aria-hidden", "true");
  state.editingProcessTemplateId = null;
  state.selectedProcessTemplateItemKey = null;
  document.body.classList.remove("modal-open");
}

function openProcessTemplateModal(templateId = null) {
  const template = state.processTemplates.find((item) => Number(item.id) === Number(templateId));
  const modal = $("#processTemplateModal");
  const form = $("#processTemplateForm");
  if (!modal || !form) return;
  state.editingProcessTemplateId = template?.id || null;
  $("#processTemplateModalTitle").textContent = template ? "编辑流程模板" : "新建流程模板";
  $("#processTemplateModalHint").textContent = template
    ? "修改只影响以后生成的流程，已经生成的个人流程保持原样。"
    : "设置每个步骤的上一步；多个起点会形成并行线路。";
  form.reset();
  form.elements.name.value = template?.name || "";
  form.elements.description.value = template?.description || "";
  form.elements.expected_version.value = template?.version || "";
  const keyById = new Map((template?.items || []).map((item) => [Number(item.id), `item-${item.id}`]));
  const items = template?.items?.length
    ? template.items.map((item) => ({
        ...item,
        _key: keyById.get(Number(item.id)),
        _parentKey: keyById.get(Number(item.parent_item_id)) || "",
      }))
    : [{ title: "", description: "", required: true, _key: nextProcessTemplateKey(), _parentKey: "" }];
  state.selectedProcessTemplateItemKey = items[0]?._key || null;
  $("#processTemplateItems").innerHTML = items.map(processTemplateItemEditor).join("");
  refreshProcessTemplateItemOrder();
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  form.elements.name.focus();
}

function processTemplatePayload(form) {
  const items = $$("#processTemplateItems [data-process-template-item]").map((row) => ({
    key: row.dataset.processItemKey || "",
    parent_key: $("[data-process-item-parent]", row)?.value || "",
    title: $("[data-process-item-title]", row)?.value.trim() || "",
    description: $("[data-process-item-description]", row)?.value.trim() || "",
    required: Boolean($("[data-process-item-required]", row)?.checked),
  }));
  if (!items.length) throw new Error("流程模板至少需要一个 Checklist");
  if (items.some((item) => !item.title)) throw new Error("请填写每个 Checklist 的标题");
  return {
    name: form.elements.name.value.trim(),
    description: form.elements.description.value.trim(),
    expected_version: form.elements.expected_version.value || undefined,
    items,
  };
}

function closeProcessStartModal() {
  $("#processStartModal")?.classList.add("hidden");
  $("#processStartModal")?.setAttribute("aria-hidden", "true");
  state.selectedProcessTemplateId = null;
  document.body.classList.remove("modal-open");
}

function openProcessStartModal(templateId) {
  const template = state.processTemplates.find((item) => Number(item.id) === Number(templateId));
  const modal = $("#processStartModal");
  const form = $("#processStartForm");
  if (!template || !modal || !form) return;
  state.selectedProcessTemplateId = template.id;
  form.reset();
  form.elements.template_id.value = template.id;
  form.elements.title.value = template.name;
  $("#processStartTemplateName").textContent = template.name;
  $("#processStartTemplateMeta").textContent = `${template.items.length} 项 Checklist${template.inherited ? ` · 来自 ${template.org_unit_name}` : ""}`;
  $("#processStartChecklistPreview").innerHTML = processFlowTreeMarkup(template.items, { compact: true });
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  form.elements.title.focus();
}

function processTreeModel(items = []) {
  const ordered = [...items].sort((a, b) => Number(a.sort_order || 0) - Number(b.sort_order || 0));
  const byId = new Map(ordered.map((item) => [Number(item.id), item]));
  const children = new Map();
  ordered.forEach((item) => {
    const parentId = Number(item.parent_item_id || 0);
    if (!parentId || !byId.has(parentId)) return;
    if (!children.has(parentId)) children.set(parentId, []);
    children.get(parentId).push(item);
  });
  let roots = ordered.filter((item) => !Number(item.parent_item_id || 0) || !byId.has(Number(item.parent_item_id)));
  if (!roots.length && ordered.length) roots = [ordered[0]];
  return { ordered, byId, children, roots };
}

function processTreeMetrics(items = []) {
  const model = processTreeModel(items);
  const depthCache = new Map();
  const depthOf = (item, trail = new Set()) => {
    if (depthCache.has(item.id)) return depthCache.get(item.id);
    const parentId = Number(item.parent_item_id || 0);
    if (!parentId || !model.byId.has(parentId) || trail.has(item.id)) return 1;
    const nextTrail = new Set(trail);
    nextTrail.add(item.id);
    const depth = depthOf(model.byId.get(parentId), nextTrail) + 1;
    depthCache.set(item.id, depth);
    return depth;
  };
  return {
    roots: model.roots.length,
    depth: model.ordered.reduce((maximum, item) => Math.max(maximum, depthOf(item)), 0),
    branches: [...model.children.values()].filter((itemsAtNode) => itemsAtNode.length > 1).length,
  };
}

function processFlowTreeMarkup(items = [], options = {}) {
  if (!items.length) return '<div class="process-flow-empty">还没有流程节点</div>';
  const { instance = false, editable = false, compact = false } = options;
  const model = processTreeModel(items);
  const orderById = new Map(model.ordered.map((item, index) => [Number(item.id), index + 1]));
  const renderNode = (item, path = new Set()) => {
    const itemId = Number(item.id);
    if (path.has(itemId)) return "";
    const nextPath = new Set(path);
    nextPath.add(itemId);
    const parent = model.byId.get(Number(item.parent_item_id || 0));
    const locked = Boolean(instance && parent && !parent.completed);
    const descendants = model.children.get(itemId) || [];
    const statusControl = instance
      ? `
        <input
          type="checkbox"
          data-process-item-toggle="${item.id}"
          data-process-item-version="${item.version}"
          aria-label="${escapeHtml(item.title)}"
          ${item.completed ? "checked" : ""}
          ${editable && !locked ? "" : "disabled"}
        />
        <span class="process-flow-check" aria-hidden="true">${item.completed ? "✓" : locked ? "…" : ""}</span>`
      : `<span class="process-flow-order">${orderById.get(itemId) || ""}</span>`;
    return `
      <li>
        <label class="process-flow-node ${item.completed ? "is-done" : ""} ${locked ? "is-locked" : ""} ${item.required ? "" : "is-optional"}">
          ${statusControl}
          <span class="process-flow-node-copy">
            <strong>${escapeHtml(item.title)}</strong>
            ${!compact && item.description ? `<small>${escapeHtml(item.description)}</small>` : ""}
            ${locked ? "<em>等待上一步</em>" : item.required ? "<em>必做</em>" : "<em>可选</em>"}
          </span>
        </label>
        ${descendants.length ? `<ul>${descendants.map((child) => renderNode(child, nextPath)).join("")}</ul>` : ""}
      </li>`;
  };
  return `
    <div class="process-flow-scroll ${compact ? "is-compact" : ""}">
      <div class="process-flow-tree">
        <ul>${model.roots.map((root) => renderNode(root)).join("")}</ul>
      </div>
    </div>`;
}

function renderProcessTemplateGraph(templates) {
  const target = $("#processTemplateGraph");
  if (!target) return;
  if (!templates.length) {
    target.innerHTML = "";
    target.classList.add("hidden");
    return;
  }
  const selected = templates.find(
    (template) => Number(template.id) === Number(state.selectedProcessTemplateGraphId),
  ) || templates[0];
  state.selectedProcessTemplateGraphId = selected.id;
  const metrics = processTreeMetrics(selected.items);
  target.classList.remove("hidden");
  target.innerHTML = `
    <div class="process-template-graph-head">
      <div>
        <span>当前流程图</span>
        <h3>${escapeHtml(selected.name)}</h3>
      </div>
      <div class="process-graph-metrics">
        <span>${metrics.roots} 条并行线</span>
        <span>${metrics.depth} 层</span>
        <span>${metrics.branches} 个分支点</span>
      </div>
    </div>
    ${processFlowTreeMarkup(selected.items)}
  `;
}

function renderProcessTemplates() {
  const target = $("#processTemplateList");
  if (!target) return;
  const templates = state.processTemplates || [];
  if (!templates.length) {
    renderProcessTemplateGraph([]);
    target.innerHTML = `
      <div class="process-empty">
        <strong>还没有可用流程模板</strong>
        <span>${canOperate("processes", "create") ? "新建一个模板，把经常重复的步骤固化下来。" : "当前账号只能查看流程模板。"}</span>
      </div>`;
    return;
  }
  renderProcessTemplateGraph(templates);
  target.innerHTML = templates.map((template) => `
    <article class="process-template-card ${Number(template.id) === Number(state.selectedProcessTemplateGraphId) ? "is-selected" : ""}">
      <div class="process-template-head">
        <div>
          <div class="process-template-title-line">
            <h3>${escapeHtml(template.name)}</h3>
            ${template.inherited ? `<span class="process-origin-badge">上级 · ${escapeHtml(template.org_unit_name)}</span>` : ""}
          </div>
          <p>${escapeHtml(template.description || "按顺序完成以下标准步骤。")}</p>
        </div>
        ${template.can_manage ? `
          <div class="process-card-menu">
            <button class="icon-button" type="button" data-process-template-edit="${template.id}" title="编辑模板" aria-label="编辑模板">✎</button>
            <button class="icon-button danger" type="button" data-process-template-delete="${template.id}" data-process-template-name="${escapeHtml(template.name)}" title="停用模板" aria-label="停用模板">×</button>
          </div>` : ""}
      </div>
      <div class="process-template-steps">
        ${template.items.slice(0, 4).map((item, index) => `
          <div><span>${index + 1}</span><strong>${escapeHtml(item.title)}</strong></div>
        `).join("")}
        ${template.items.length > 4 ? `<small>还有 ${template.items.length - 4} 项</small>` : ""}
      </div>
      <div class="process-template-footer">
        <span>${template.items.length} 项 Checklist · 已生成 ${Number(template.instance_count || 0)} 次</span>
        <div>
          <button class="secondary" type="button" data-process-template-graph="${template.id}">查看流程图</button>
          ${canOperate("processes", "create") && state.user ? `<button type="button" data-process-start="${template.id}">生成我的流程</button>` : ""}
        </div>
      </div>
    </article>
  `).join("");
}

function renderProcessInstances() {
  const target = $("#processInstanceList");
  if (!target) return;
  const instances = state.processInstances || [];
  if (!instances.length) {
    target.innerHTML = `
      <div class="process-empty">
        <strong>${state.processStatus === "completed" ? "还没有已完成流程" : "当前没有进行中的流程"}</strong>
        <span>${state.processStatus === "active" ? "从上方模板生成一个个人流程即可开始。" : "完成全部必做项后会自动归档到这里。"}</span>
      </div>`;
    return;
  }
  target.innerHTML = instances.map((instance, index) => {
    const editable = Boolean(instance.can_edit) && canOperate("processes", "edit");
    const itemMap = new Map(instance.items.map((item) => [Number(item.id), item]));
    const view = state.processInstanceViews[instance.id] || "graph";
    const checklistMarkup = instance.items.map((item) => {
      const parent = itemMap.get(Number(item.parent_item_id || 0));
      const locked = Boolean(parent && !parent.completed);
      return `
        <label class="process-check-item ${item.completed ? "is-done" : ""} ${locked ? "is-locked" : ""}">
          <input type="checkbox" data-process-item-toggle="${item.id}" data-process-item-version="${item.version}" ${item.completed ? "checked" : ""} ${editable && !locked ? "" : "disabled"} />
          <span class="process-check-control" aria-hidden="true"></span>
          <span class="process-check-copy">
            <strong>${escapeHtml(item.title)}</strong>
            ${item.description ? `<small>${escapeHtml(item.description)}</small>` : ""}
            ${parent ? `<small class="process-parent-copy">上一步：${escapeHtml(parent.title)}</small>` : '<small class="process-parent-copy">并行起点</small>'}
            ${item.completed_at ? `<em>${escapeHtml(item.completed_by_name || "成员")} · ${escapeHtml(shortDateTime(item.completed_at))}</em>` : locked ? "<em>等待上一步完成</em>" : ""}
          </span>
          ${item.required ? '<span class="process-required-badge">必做</span>' : '<span class="process-optional-badge">可选</span>'}
        </label>`;
    }).join("");
    return `
      <details class="process-instance-card ${instance.status === "completed" ? "is-completed" : ""} ${instance.overdue ? "is-overdue" : ""}" ${index === 0 && state.processStatus === "active" ? "open" : ""}>
        <summary>
          <div class="process-instance-summary-main">
            <span class="process-status-mark">${instance.status === "completed" ? "✓" : instance.overdue ? "!" : "→"}</span>
            <div>
              <h3>${escapeHtml(instance.title)}</h3>
              <p>${escapeHtml(instance.owner_name)} · ${escapeHtml(instance.template_name || "历史模板")} · 开始于 ${escapeHtml(shortDate(instance.started_at))}</p>
            </div>
          </div>
          <div class="process-progress-summary">
            <strong>${Number(instance.progress || 0)}%</strong>
            <span>必做 ${Number(instance.required_completed || 0)} / ${Number(instance.required_total || 0)}</span>
          </div>
        </summary>
        <div class="process-progress-track"><span style="width:${Number(instance.progress || 0)}%"></span></div>
        <div class="process-instance-meta">
          <div>
            <span>${instance.status === "completed" ? `完成于 ${escapeHtml(shortDateTime(instance.completed_at))}` : instance.due_date ? `截止 ${escapeHtml(shortDate(instance.due_date))}` : "未设置截止日期"}</span>
            ${instance.overdue ? '<span class="process-overdue-badge">已逾期</span>' : ""}
            ${state.processScope === "team" ? `<span>${escapeHtml(instance.org_unit_name || "")}</span>` : ""}
          </div>
          <div class="segmented-control process-instance-view-switch" role="group" aria-label="流程展示方式">
            <button class="${view === "graph" ? "active" : ""}" type="button" data-process-instance-view="${instance.id}" data-process-view="graph">流程图</button>
            <button class="${view === "list" ? "active" : ""}" type="button" data-process-instance-view="${instance.id}" data-process-view="list">清单</button>
          </div>
        </div>
        ${view === "graph"
          ? `<div class="process-instance-graph">${processFlowTreeMarkup(instance.items, { instance: true, editable })}</div>`
          : `<div class="process-checklist">${checklistMarkup}</div>`}
        ${editable && canOperate("processes", "delete") ? `
          <div class="process-instance-actions">
            <button class="secondary danger" type="button" data-process-instance-delete="${instance.id}" data-process-instance-name="${escapeHtml(instance.title)}">取消流程</button>
          </div>` : ""}
      </details>
    `;
  }).join("");
}

function renderProcesses() {
  const active = state.processInstances.filter((item) => item.status === "active").length;
  const completed = state.processInstances.filter((item) => item.status === "completed").length;
  const overdue = state.processInstances.filter((item) => item.overdue).length;
  const stats = $("#processStats");
  if (stats) {
    stats.innerHTML = `
      <div><span>可用模板</span><strong>${state.processTemplates.length}</strong></div>
      <div><span>当前列表</span><strong>${state.processInstances.length}</strong></div>
      <div><span>进行中</span><strong>${active}</strong></div>
      <div class="${overdue ? "is-alert" : ""}"><span>已逾期</span><strong>${overdue}</strong></div>
      <div><span>已完成</span><strong>${completed}</strong></div>
    `;
  }
  $("#openProcessTemplateBtn")?.classList.toggle("hidden", !state.user || !canOperate("processes", "create"));
  $$("[data-process-scope]").forEach((button) => {
    button.classList.toggle("active", button.dataset.processScope === state.processScope);
    button.classList.toggle("hidden", button.dataset.processScope === "team" && !isAdminView());
  });
  $$("[data-process-status]").forEach((button) => {
    button.classList.toggle("active", button.dataset.processStatus === state.processStatus);
  });
  renderProcessTemplates();
  renderProcessInstances();
}

async function loadProcesses() {
  if (!canLoadModule("processes") || !state.user) return;
  if (!isAdminView()) state.processScope = "mine";
  const query = new URLSearchParams({
    scope: state.processScope,
    status: state.processStatus,
  });
  const [templates, instances] = await Promise.all([
    api("/api/process-templates"),
    api(`/api/process-instances?${query}`),
  ]);
  state.processTemplates = templates.templates || [];
  state.processInstances = instances.instances || [];
  renderProcesses();
}

async function loadUsers() {
  if (!isAdminView()) return;
  const [data, typeData, orgData] = await Promise.all([
    api("/api/users"),
    api("/api/user-types"),
    api("/api/org-units"),
  ]);
  state.users = data.users;
  const currentAccount = state.users.find((item) => Number(item.id) === Number(state.user?.id));
  if (state.user && currentAccount) state.user = { ...state.user, ...currentAccount };
  state.userTypes = typeData.types;
  state.moduleCatalog = typeData.modules;
  state.orgUnits = orgData.units || [];
  state.selectedUserIds.clear();
  populateUserManagementFilters();
  renderUserManagement();
  renderUserTypePermissions();
  renderOrgUnits();
  populateSelects();
}

function renderUserTypeOptions(selected, includeGuest = false) {
  const options = state.userTypes.filter((type) => includeGuest || (!type.is_guest && type.key !== "guest"));
  return options.map((type) => `<option value="${escapeHtml(type.key)}" ${type.key === selected ? "selected" : ""}>${escapeHtml(type.name)}</option>`).join("");
}

function renderOrgOptions(selected, excludeId = null, includeRoot = false) {
  const rootOption = includeRoot ? '<option value="">无上级（根团队）</option>' : "";
  return `${rootOption}${state.orgUnits
    .filter((unit) => Number(unit.id) !== Number(excludeId))
    .map((unit) => `<option value="${unit.id}" ${Number(unit.id) === Number(selected) ? "selected" : ""}>${"　".repeat(Number(unit.depth || 0))}${escapeHtml(unit.name)}</option>`)
    .join("")}`;
}

function renderOrgUnits() {
  const target = $("#orgUnitList");
  if (!target) return;
  const visibilityLabels = { all: "全部组织", subtree: "当前及下级", unit: "仅当前团队" };
  target.innerHTML = state.orgUnits.length ? state.orgUnits.map((unit) => `
    <article class="org-unit-row" style="--org-depth:${Number(unit.depth || 0)}">
      <div class="org-unit-main">
        <span class="org-tree-mark"></span>
        <div><strong>${escapeHtml(unit.name)}</strong><small>${escapeHtml(unit.route)}</small></div>
      </div>
      <div class="org-unit-meta">
        <span class="pill">${escapeHtml(visibilityLabels[unit.visibility_mode] || unit.visibility_mode)}</span>
        <span>${Number(unit.user_count || 0)} 人</span>
        <span>${unit.sso_groups?.length ? `SSO：${escapeHtml(unit.sso_groups.join("、"))}` : "未映射 SSO 群组"}</span>
      </div>
      <div class="org-unit-actions"><button class="secondary org-unit-edit-btn" type="button" data-org-unit-id="${unit.id}">编辑</button><button class="danger org-unit-delete-btn" type="button" data-org-unit-id="${unit.id}" data-org-unit-name="${escapeHtml(unit.name)}">删除</button></div>
    </article>`).join("") : '<p class="empty-note">暂无团队层级。</p>';
}

function openOrgUnitModal(orgUnitId = null) {
  const form = $("#orgUnitForm");
  const modal = $("#orgUnitModal");
  if (!form || !modal) return;
  const unit = state.orgUnits.find((item) => Number(item.id) === Number(orgUnitId));
  form.reset();
  form.elements.id.value = unit?.id || "";
  form.elements.name.value = unit?.name || "";
  form.elements.slug.value = unit?.slug || "";
  form.elements.parent_id.innerHTML = renderOrgOptions(unit?.parent_id, unit?.id, true);
  form.elements.parent_id.value = unit?.parent_id || "";
  form.elements.visibility_mode.value = unit?.visibility_mode || "unit";
  form.elements.default_user_type.innerHTML = renderUserTypeOptions(unit?.default_user_type || "default");
  form.elements.default_user_type.value = unit?.default_user_type || state.userTypes.find((type) => !type.is_guest)?.key || "default";
  form.elements.sort_order.value = Number(unit?.sort_order || 0);
  form.elements.sso_groups.value = (unit?.sso_groups || []).join("\n");
  $("#orgUnitModalTitle").textContent = unit ? `编辑团队：${unit.name}` : "新增团队";
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  form.elements.name.focus();
}

function closeOrgUnitModal() {
  const modal = $("#orgUnitModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

function userAuthGroup(user) {
  if (user.role === "admin") return "admin";
  return user.auth_source === "oidc" || user.auth_source === "oauth2" ? "sso" : "local";
}

function filteredManagementUsers() {
  const filters = state.userFilters;
  const query = filters.query.trim().toLocaleLowerCase("zh-CN");
  return state.users.filter((user) => {
    const searchable = [
      user.username,
      user.employee_id,
      user.display_name,
      user.org_unit_name,
      user.suggested_org_unit_name,
      ...(user.sso_groups || []),
    ].filter(Boolean).join(" ").toLocaleLowerCase("zh-CN");
    return (!query || searchable.includes(query))
      && (!filters.org || String(user.org_unit_id || "") === filters.org)
      && (!filters.type || user.user_type === filters.type)
      && (!filters.auth || userAuthGroup(user) === filters.auth);
  });
}

function populateUserManagementFilters() {
  const orgFilter = $("#userOrgFilter");
  const typeFilter = $("#userTypeFilter");
  if (state.userFilters.org && !state.orgUnits.some((unit) => String(unit.id) === state.userFilters.org)) state.userFilters.org = "";
  if (state.userFilters.type && !state.userTypes.some((type) => type.key === state.userFilters.type)) state.userFilters.type = "";
  if (orgFilter) {
    orgFilter.innerHTML = `<option value="">全部团队</option>${renderOrgOptions(state.userFilters.org)}`;
    orgFilter.value = state.userFilters.org;
  }
  if (typeFilter) {
    typeFilter.innerHTML = `<option value="">全部类型</option>${renderUserTypeOptions(state.userFilters.type, true)}`;
    typeFilter.value = state.userFilters.type;
  }
  if ($("#userSearchInput")) $("#userSearchInput").value = state.userFilters.query;
  if ($("#userAuthFilter")) $("#userAuthFilter").value = state.userFilters.auth;
}

function renderUserManagement() {
  const users = filteredManagementUsers();
  const result = $("#userFilterResult");
  const pendingCount = state.users.filter((user) => Boolean(user.classification_pending)).length;
  if (result) result.textContent = `${users.length === state.users.length ? `共 ${users.length} 个账号` : `找到 ${users.length} / ${state.users.length} 个账号`}${pendingCount ? ` · 待分类 ${pendingCount}` : ""}`;
  if ($("#userList")) $("#userList").innerHTML = renderUserTable(users);
  updateUserBulkToolbar();
}

function renderUserTable(users) {
  if (!users.length) return '<div class="user-filter-empty"><strong>没有匹配的账号</strong><span>调整搜索词或筛选条件后再试。</span></div>';
  return `<div class="user-table-wrap"><table class="user-management-table"><thead><tr><th class="user-select-col"><input id="userBulkSelectAll" type="checkbox" aria-label="全选账号"></th><th>账号 / 工号</th><th>姓名</th><th>所属团队</th><th>用户类型</th><th>授权方式</th><th>业务参与</th><th>操作</th></tr></thead><tbody>${users.map((user) => `
    <tr class="${user.classification_pending ? "user-row-pending" : ""}">
      <td class="user-select-col"><input class="user-bulk-checkbox" type="checkbox" value="${user.id}" aria-label="选择 ${escapeHtml(user.display_name)}" ${Number(user.id) === Number(state.user?.id) ? "disabled title=\"当前登录账号不能批量操作\"" : state.selectedUserIds.has(Number(user.id)) ? "checked" : ""}></td>
      <td><strong>${escapeHtml(user.username)}</strong><small>工号 ${escapeHtml(user.employee_id || user.username)}</small></td>
      <td>${escapeHtml(user.display_name)}</td>
      <td><div class="user-org-assignment"><span class="pill org-pill">${escapeHtml(user.org_unit_name || "未分配")}</span>${user.suggested_org_unit_name ? `<small>SSO 建议 → ${escapeHtml(user.suggested_org_unit_name)}</small>` : ""}</div></td>
      <td>${user.classification_pending
        ? '<span class="pill user-pending-pill">待分类 · 访客权限</span>'
        : `<span class="pill">${escapeHtml(user.user_type_name || user.user_type)}</span>`}</td>
      <td>${user.role === "admin" ? '<span class="pill admin">系统管理员</span>' : user.auth_source === "oidc" || user.auth_source === "oauth2" ? '<span class="pill status-done">企业 SSO</span>' : "系统账号"}</td>
      <td><div class="user-scope-mini">${[
        ["members", "成员"], ["morning", "早会"], ["rules", "榜单"], ["thanks", "感谢"],
      ].map(([scope, label]) => `<span class="${Boolean(user[`eligible_${scope}`]) ? "on" : "off"}">${label}</span>`).join("")}</div></td>
      <td class="user-row-actions">
        <button class="secondary user-account-edit-btn" type="button" data-user-id="${user.id}">编辑</button>
        ${user.id !== state.user?.id ? `<button class="danger user-delete-btn" data-user-id="${user.id}" data-user-name="${escapeHtml(user.display_name)}">删除</button>` : `<span class="pill">当前账号</span>`}
      </td>
    </tr>`).join("")}</tbody></table></div>`;
}

function selectedBulkUserIds() {
  return [...state.selectedUserIds].filter((userId) => state.users.some((user) => Number(user.id) === Number(userId)));
}

function updateUserBulkToolbar() {
  const selected = selectedBulkUserIds();
  $("#userBulkToolbar")?.classList.toggle("hidden", selected.length === 0);
  if ($("#userBulkCount")) $("#userBulkCount").textContent = String(selected.length);
  const checkboxes = $$(".user-bulk-checkbox:not(:disabled)");
  const selectAll = $("#userBulkSelectAll");
  if (selectAll) {
    const visibleSelected = checkboxes.filter((input) => state.selectedUserIds.has(Number(input.value))).length;
    selectAll.checked = checkboxes.length > 0 && visibleSelected === checkboxes.length;
    selectAll.indeterminate = visibleSelected > 0 && visibleSelected < checkboxes.length;
  }
}

function clearUserBulkSelection() {
  state.selectedUserIds.clear();
  renderUserManagement();
}

function updateUserBulkActionOptions() {
  const action = $("#userBulkAction")?.value || "";
  const target = $("#userBulkTarget");
  const execute = $("#userBulkExecuteBtn");
  if (!target || !execute) return;
  target.classList.toggle("hidden", !["type", "org"].includes(action));
  execute.classList.toggle("danger", action === "delete");
  execute.textContent = action === "delete" ? "删除所选" : "应用";
  if (action === "type") {
    target.innerHTML = `<option value="">选择目标类型</option>${renderUserTypeOptions("")}`;
    target.setAttribute("aria-label", "选择目标用户类型");
  } else if (action === "org") {
    target.innerHTML = `<option value="">选择目标团队</option>${renderOrgOptions("")}`;
    target.setAttribute("aria-label", "选择目标团队");
  } else {
    target.innerHTML = "";
  }
  execute.disabled = !action || (["type", "org"].includes(action) && !target.value);
}

function openUserAccountModal(userId) {
  const user = state.users.find((item) => Number(item.id) === Number(userId));
  const form = $("#userAccountEditForm");
  if (!user || !form) return;
  form.dataset.userId = String(user.id);
  form.elements.username.value = user.username || "";
  form.elements.employee_id.value = user.employee_id || user.username || "";
  form.elements.display_name.value = user.display_name || "";
  form.elements.org_unit_id.innerHTML = renderOrgOptions(user.org_unit_id);
  form.elements.org_unit_id.value = user.org_unit_id || "";
  const suggestion = $("#userSuggestedOrg");
  const suggestionName = $("#userSuggestedOrgName");
  const suggestionButton = $("#userUseSuggestedOrgBtn");
  suggestion?.classList.toggle("hidden", !user.suggested_org_unit_id);
  if (suggestionName) suggestionName.textContent = user.suggested_org_unit_name || "";
  if (suggestionButton) suggestionButton.dataset.orgUnitId = user.suggested_org_unit_id || "";
  form.elements.user_type.innerHTML = renderUserTypeOptions(user.user_type);
  form.elements.user_type.value = user.user_type;
  form.elements.role.value = user.role || "user";
  form.elements.role.disabled = Number(user.id) === Number(state.user?.id);
  form.elements.password.value = "";
  $("#userAccountModalTitle").textContent = `编辑账号：${user.display_name}`;
  const modal = $("#userAccountModal");
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  form.elements.username.focus();
}

function closeUserAccountModal() {
  const modal = $("#userAccountModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

function renderUserTypePermissions() {
  const target = $("#userTypePermissionList");
  if (!target) return;
  if (!state.userTypes.length || !state.moduleCatalog.length) {
    target.innerHTML = "<p>暂无用户类型配置</p>";
    return;
  }
  const scopeLabels = { members: "团队成员", morning: "早例会", rules: "红黑榜", thanks: "Thank You" };
  target.innerHTML = state.userTypes.map((type) => {
    const isGuestType = Boolean(type.is_guest || type.key === "guest");
    const visibleModules = state.moduleCatalog.filter((module) => Boolean(type.permissions?.[module.key]?.view));
    const participation = type.participation || {};
    return `
      <article class="user-type-summary-card ${isGuestType ? "guest" : ""}">
        <div class="user-type-summary-head">
          <div><strong>${escapeHtml(type.name)}</strong><span>${isGuestType ? `未登录 + ${Number(type.user_count || 0)} 个待分类账号` : `${Number(type.user_count || 0)} 个账号`}</span></div>
          <button class="user-type-config-btn" type="button" data-type-key="${escapeHtml(type.key)}">配置</button>
        </div>
        <p>${escapeHtml(type.description || "尚未填写类型说明")}</p>
        <div class="user-type-summary-row"><span>可访问模块</span><div>${visibleModules.length ? visibleModules.map((module) => `<span class="scope-chip module">${escapeHtml(module.name)}</span>`).join("") : '<span class="scope-chip off">无</span>'}</div></div>
        ${isGuestType ? "" : `<div class="user-type-summary-row"><span>参与名单</span><div>${Object.entries(scopeLabels).map(([scope, label]) => `<span class="scope-chip ${participation[scope] ? "on" : "off"}">${label}</span>`).join("")}</div></div>`}
        <div class="user-type-summary-actions">
          <button class="secondary permission-preview-btn" type="button" data-type-key="${escapeHtml(type.key)}">预览视图</button>
          ${isGuestType
            ? ""
            : Number(type.user_count || 0) > 0
              ? `<span class="user-type-delete-note">迁移账号后可删除</span>`
              : `<button class="danger user-type-delete-btn" type="button" data-type-key="${escapeHtml(type.key)}" data-type-name="${escapeHtml(type.name)}">删除类型</button>`}
        </div>
      </article>
    `;
  }).join("");
}

function renderUserTypePermissionEditor(type) {
  const target = $("#userTypePermissionEditor");
  if (!target || !type) return;
  const isGuestType = Boolean(type.is_guest || type.key === "guest");
  const legacyModules = new Set(type.modules || []);
  const actions = isGuestType ? [["view", "可查看"]] : [["view", "查看"], ["create", "新增"], ["edit", "编辑"], ["delete", "删除"]];
  const scopeLabels = { members: "团队成员展示", morning: "早例会跟踪", rules: "红黑榜名单", thanks: "Thank You 名单" };
  target.innerHTML = `<form class="user-type-permission-form" data-type-key="${escapeHtml(type.key)}">
    <input type="hidden" name="expected_version" value="${Number(type.version || 1)}">
    <div class="permission-modal-identity">
      <label>类型名称<input name="name" value="${escapeHtml(type.name)}" maxlength="30" ${isGuestType ? "disabled" : ""}></label>
      <label>类型说明<input name="description" value="${escapeHtml(type.description || "")}" maxlength="200" ${isGuestType ? "disabled" : ""} placeholder="说明适用对象和使用边界"></label>
    </div>
    <section class="permission-modal-section ${isGuestType ? "hidden" : ""}">
      <div class="permission-section-title"><strong>业务参与名单</strong><span>与页面访问权限相互独立</span></div>
      <div class="participation-grid">${Object.entries(scopeLabels).map(([scope, label]) => `<label class="participation-toggle"><input type="checkbox" name="participation" value="${scope}" ${type.participation?.[scope] ? "checked" : ""}><span><strong>${label}</strong><small>${scope === "members" ? "显示成员卡片" : scope === "morning" ? "可登记和被跟踪事项" : scope === "rules" ? "可记录并进入积分看板" : "可被感谢并进入排名"}</small></span></label>`).join("")}</div>
    </section>
    <section class="permission-modal-section">
      <div class="permission-section-title"><strong>模块操作权限</strong><span>${isGuestType ? "访客仅支持查看" : "操作权限会自动包含查看权限"}</span></div>
      <div class="permission-matrix-wrap"><table class="permission-matrix"><thead><tr><th>模块</th>${actions.map(([, label]) => `<th>${label}</th>`).join("")}</tr></thead><tbody>${state.moduleCatalog.map((module) => {
        const modulePermissions = type.permissions?.[module.key] || {};
        const guestUnsupported = isGuestType && module.key === "dashboard";
        return `<tr><th><strong>${escapeHtml(module.name)}</strong><small>${guestUnsupported ? "访客不可用" : escapeHtml(module.description || "")}</small></th>${actions.map(([action, label]) => {
          const checked = !guestUnsupported && (modulePermissions[action] ?? legacyModules.has(module.key));
          return `<td><label class="permission-action-check ${guestUnsupported ? "disabled" : ""}" title="${escapeHtml(module.name)} · ${label}"><input type="checkbox" name="permission" value="${escapeHtml(module.key)}:${action}" data-permission-module="${escapeHtml(module.key)}" data-permission-action="${action}" ${checked ? "checked" : ""} ${guestUnsupported ? "disabled" : ""}><span>${guestUnsupported ? "需登录" : label}</span></label></td>`;
        }).join("")}</tr>`;
      }).join("")}</tbody></table></div>
    </section>
    <div class="permission-impact-summary" data-permission-impact><strong>当前配置</strong><span>${isGuestType ? "影响所有未登录访客" : `关联 ${Number(type.user_count || 0)} 个账号${type.assigned_users?.length ? `：${escapeHtml(type.assigned_users.join("、"))}` : ""}`}</span></div>
    <div class="modal-actions permission-modal-actions"><button class="secondary" type="button" data-user-type-modal-close>取消</button><button class="secondary permission-preview-btn" type="button" data-type-key="${escapeHtml(type.key)}">预览视图</button><button class="secondary permission-impact-btn" type="button" data-type-key="${escapeHtml(type.key)}">评估影响</button><button type="submit">保存配置</button></div>
  </form>`;
}

function openUserTypePermissionModal(typeKey) {
  const type = state.userTypes.find((item) => item.key === typeKey);
  if (!type) return;
  renderUserTypePermissionEditor(type);
  $("#userTypePermissionTitle").textContent = `配置：${type.name}`;
  $("#userTypePermissionSubtitle").textContent = type.is_guest ? "设置未登录访客可以查看的模块。" : "页面权限与业务参与名单分开设置。";
  const modal = $("#userTypePermissionModal");
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}

function closeUserTypePermissionModal() {
  const modal = $("#userTypePermissionModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

function permissionFormPermissions(form) {
  const permissions = {};
  state.moduleCatalog.forEach((module) => {
    permissions[module.key] = { view: false, create: false, edit: false, delete: false };
  });
  new FormData(form).getAll("permission").forEach((value) => {
    const [moduleKey, action] = String(value).split(":");
    if (permissions[moduleKey] && Object.hasOwn(permissions[moduleKey], action)) permissions[moduleKey][action] = true;
  });
  return permissions;
}

function permissionFormParticipation(form) {
  const selected = new Set(new FormData(form).getAll("participation").map(String));
  return {
    members: selected.has("members"),
    morning: selected.has("morning"),
    rules: selected.has("rules"),
    thanks: selected.has("thanks"),
  };
}

async function assessPermissionImpact(form) {
  const target = form.querySelector("[data-permission-impact]");
  if (target) target.innerHTML = "<strong>正在评估</strong><span>对比服务器上的最新权限…</span>";
  const data = await api(`/api/user-types/${form.dataset.typeKey}/impact`, {
    method: "POST",
    body: JSON.stringify({
      permissions: permissionFormPermissions(form),
      participation: permissionFormParticipation(form),
    }),
  });
  const enabled = (data.changed || []).filter((item) => item.enabled);
  const disabled = (data.changed || []).filter((item) => !item.enabled);
  const users = data.affected_users?.length ? `：${data.affected_users.join("、")}` : "";
  const scopeChanges = data.participation_changed || [];
  const totalChanges = (data.changed || []).length + scopeChanges.length;
  const scopeSummary = scopeChanges.length ? `；调整名单：${scopeChanges.map((item) => `${item.enabled ? "加入" : "移出"}${item.name}`).join("、")}` : "";
  if (target) target.innerHTML = totalChanges
    ? `<strong>将变更 ${totalChanges} 项配置</strong><span>权限新增 ${enabled.length} 项、收回 ${disabled.length} 项${escapeHtml(scopeSummary)}；影响 ${data.affected_count} 个账号${escapeHtml(users)}</span>`
    : `<strong>配置没有变化</strong><span>关联 ${data.affected_count} 个账号${escapeHtml(users)}</span>`;
  return data;
}

async function loadSystemAdmin() {
  if (!isAdminView()) return;
  const [settings, backups, logs, recycle] = await Promise.all([
    api("/api/settings"),
    api("/api/backups"),
    api("/api/audit-logs?limit=120"),
    api("/api/recycle-bin"),
  ]);
  state.settings = settings.settings;
  state.backups = backups.backups;
  state.auditLogs = logs.logs;
  state.recycleBin = recycle.items || [];
  renderSettings();
  renderBackups();
  renderAuditLogs();
  renderRecycleBin();
  applyBranding();
  applySettingDefaults();
}

function renderRecycleBin() {
  const target = $("#recycleBinList");
  if (!target) return;
  target.innerHTML = state.recycleBin.length ? state.recycleBin.map((item) => `
    <article class="recycle-item">
      <div class="recycle-item-main">
        <span class="pill">${escapeHtml(item.entity_label || item.entity_type)}</span>
        <div>
          <strong>${escapeHtml(item.title || "未命名内容")}</strong>
          <small>${escapeHtml(item.deleted_by_name || "系统")} · ${escapeHtml(shortDateTime(item.deleted_at || ""))}</small>
        </div>
      </div>
      <div class="recycle-item-actions">
        <button class="secondary recycle-restore-btn" type="button" data-recycle-id="${item.id}">恢复</button>
        ${item.can_purge ? `<button class="danger recycle-purge-btn" type="button" data-recycle-id="${item.id}" data-recycle-title="${escapeHtml(item.title || "该内容")}">彻底删除</button>` : '<span class="pill">保留历史</span>'}
      </div>
    </article>`).join("") : '<p class="empty-note">回收站为空</p>';
}

function renderReminders(unread = state.reminders.filter((item) => !item.read).length) {
  const badge = $("#reminderBadge");
  if (badge) {
    badge.textContent = String(unread);
    badge.classList.toggle("hidden", unread < 1);
  }
  const summary = $("#reminderSummary");
  if (summary) summary.textContent = unread ? `${unread} 条未读提醒` : "暂无未读提醒";
  const readAll = $("#reminderReadAllBtn");
  if (readAll) readAll.disabled = unread < 1;
  const list = $("#reminderList");
  if (!list) return;
  list.innerHTML = state.reminders.length ? state.reminders.map((item) => `
    <button class="reminder-item reminder-${escapeHtml(item.level || "info")} ${item.read ? "is-read" : ""}" type="button" data-reminder-key="${escapeHtml(item.key)}" data-reminder-page="${escapeHtml(item.page)}">
      <span class="reminder-dot"></span>
      <span class="reminder-content">
        <strong>${escapeHtml(item.title)}</strong>
        <span>${escapeHtml(item.detail || "")}</span>
        <small>${escapeHtml(shortDate(item.date || ""))}</small>
      </span>
    </button>`).join("") : '<p class="empty-note">近期没有需要处理的提醒</p>';
}

async function loadReminders() {
  if (isGuest()) return;
  const data = await api("/api/reminders");
  state.reminders = data.items || [];
  renderReminders(Number(data.unread || 0));
}

function openReminderModal() {
  const modal = $("#reminderModal");
  if (!modal || isGuest()) return;
  renderReminders();
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}

function closeReminderModal() {
  const modal = $("#reminderModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

async function markRemindersRead(keys = [], all = false) {
  const data = await api("/api/reminders/read", {
    method: "PATCH",
    body: JSON.stringify({ keys, all }),
  });
  state.reminders = data.items || [];
  renderReminders(Number(data.unread || 0));
}

function renderSettingField(setting) {
  const key = escapeHtml(setting.key);
  const modeClass = setting.key === "sso_issuer_url" ? " sso-discovery-only" : ["sso_authorization_url", "sso_token_url", "sso_userinfo_url"].includes(setting.key) ? " sso-manual-only" : "";
  if (setting.key === "sso_mode") {
    return `<label class="setting-field">
      <span>${escapeHtml(setting.label)}</span>
      <select name="${key}" id="ssoModeSelect">
        <option value="discovery" ${setting.value !== "manual" ? "selected" : ""}>OIDC 自动发现（推荐）</option>
        <option value="manual" ${setting.value === "manual" ? "selected" : ""}>手动 OAuth2 端点</option>
      </select>
      <small>${escapeHtml(setting.description || "")}</small>
    </label>`;
  }
  if (setting.value_type === "boolean") {
    return `<label class="setting-field">
      <span>${escapeHtml(setting.label)}</span>
      <select name="${key}">
        <option value="1" ${setting.value === "1" ? "selected" : ""}>启用</option>
        <option value="0" ${setting.value === "0" ? "selected" : ""}>停用</option>
      </select>
      <small>${escapeHtml(setting.description || "")}</small>
    </label>`;
  }
  if (setting.key === "sso_default_user_type") {
    return `<label class="setting-field">
      <span>${escapeHtml(setting.label)}</span>
      <input name="${key}" type="hidden" value="guest">
      <input value="访客 / 待分类（只读）" disabled>
      <small>${escapeHtml(setting.description || "")}</small>
    </label>`;
  }
  const inputType = setting.value_type === "number" ? "number" : setting.value_type === "password" ? "password" : "text";
  const placeholder = setting.value_type === "password" && setting.configured ? "已配置，留空保持不变" : "";
  const ssoAutocomplete = setting.key === "sso_client_secret"
    ? ' autocomplete="new-password" data-lpignore="true" data-1p-ignore="true"'
    : setting.key.startsWith("sso_")
      ? ' autocomplete="off" autocapitalize="off" spellcheck="false" data-lpignore="true" data-1p-ignore="true"'
      : "";
  return `<label class="setting-field${modeClass}" data-setting-key="${key}" data-configured="${setting.configured ? "true" : "false"}">
    <span>${escapeHtml(setting.label)}</span>
    <input name="${key}" type="${inputType}" value="${escapeHtml(setting.value || "")}" placeholder="${placeholder}"${ssoAutocomplete}>
    <small>${escapeHtml(setting.description || "")}</small>
  </label>`;
}

function renderSettings() {
  const form = $("#settingsForm");
  if (!form) return;
  const ssoSettings = state.settings.filter((setting) => setting.key.startsWith("sso_"));
  const ssoByKey = new Map(ssoSettings.map((setting) => [setting.key, setting]));
  const renderSsoFields = (keys) => keys.map((key) => ssoByKey.get(key)).filter(Boolean).map(renderSettingField).join("");
  const generalSettings = state.settings.filter((setting) => !setting.key.startsWith("sso_"));
  const storedMode = ssoByKey.get("sso_mode")?.value === "manual" ? "manual" : "discovery";
  const storedRequired = storedMode === "manual"
    ? ["sso_authorization_url", "sso_token_url", "sso_userinfo_url", "sso_client_id"]
    : ["sso_issuer_url", "sso_client_id"];
  const storedComplete = storedRequired.every((key) => Boolean(ssoByKey.get(key)?.value));
  const storedEnabled = ssoByKey.get("sso_enabled")?.value === "1";
  form.innerHTML = `
    <div class="settings-grid">
      ${generalSettings.map(renderSettingField).join("")}
    </div>
    <details class="settings-group" open>
      <summary>企业 SSO 登录</summary>
      <div class="settings-group-note sso-provider-note">
        <span>已知认证、Access Token、UserInfo 三个地址时，选择“手动 OAuth2 端点”并按顺序填写即可。系统使用授权码 + PKCE。</span>
        <button id="ssoOneAccessPresetBtn" class="secondary" type="button">应用华为云 OneAccess 预设</button>
      </div>
      <div class="sso-setup-head">
        <div class="sso-mode-field">${renderSsoFields(["sso_mode"])}</div>
        <div id="ssoConfigReadiness" class="sso-config-readiness" aria-live="polite"></div>
      </div>
      <section class="sso-config-section">
        <div><strong>启用与建号策略</strong><span>新账号先进入访客 / 待分类，等待管理员分配用户类型和团队。</span></div>
        <div class="settings-grid">${renderSsoFields(["sso_enabled", "sso_auto_login", "sso_auto_provision"])}</div>
      </section>
      <section class="sso-config-section sso-discovery-only">
        <div><strong>OIDC 自动发现</strong><span>身份平台提供 Issuer 时只需填写一个入口。</span></div>
        <div class="settings-grid">${renderSsoFields(["sso_issuer_url"])}</div>
      </section>
      <section class="sso-config-section sso-manual-only">
        <div><strong>OAuth2 服务地址</strong><span>直接粘贴身份平台提供的三个地址。</span></div>
        <div class="sso-endpoint-stack">
          ${renderSsoFields(["sso_authorization_url", "sso_token_url", "sso_userinfo_url"])}
        </div>
      </section>
      <section class="sso-config-section">
        <div><strong>应用凭据与回调</strong><span>Client Secret 留空表示保持原配置不变。</span></div>
        <div class="settings-grid">${renderSsoFields(["sso_client_id", "sso_client_secret", "sso_redirect_uri", "sso_scopes"])}</div>
      </section>
      <details class="sso-advanced-settings">
        <summary>字段映射与登录策略</summary>
        <div class="settings-grid">${renderSsoFields(["sso_username_claim", "sso_display_name_claim", "sso_group_claim", "sso_button_label", "sso_default_user_type"])}</div>
      </details>
      <div class="sso-save-actions">
        <div id="ssoPersistedState" class="sso-persisted-state ${storedComplete ? "is-saved" : ""}">
          <strong>${storedComplete ? (storedEnabled ? "已保存并启用" : "已保存，尚未启用") : "当前数据库尚未保存完整 SSO 配置"}</strong>
          <span>${storedComplete ? "可运行诊断确认 UserInfo 映射" : "填写后必须点击右侧保存按钮"}</span>
        </div>
        <button id="ssoDiagnoseBtn" class="secondary" type="button">诊断已保存配置</button>
        <button type="submit">保存 SSO 配置</button>
      </div>
    </details>
    <button>保存全部系统配置</button>`;
  updateSsoModeFields();
}

function updateSsoModeFields() {
  const manual = $("#ssoModeSelect")?.value === "manual";
  $$(".sso-discovery-only").forEach((field) => field.classList.toggle("hidden", manual));
  $$(".sso-manual-only").forEach((field) => field.classList.toggle("hidden", !manual));
  const readiness = $("#ssoConfigReadiness");
  if (!readiness) return;
  const valueOf = (key) => $(`#settingsForm [name="${key}"]`)?.value.trim() || "";
  const required = manual
    ? [
        ["sso_authorization_url", "认证地址"],
        ["sso_token_url", "Access Token 地址"],
        ["sso_userinfo_url", "UserInfo 地址"],
        ["sso_client_id", "Client ID"],
      ]
    : [["sso_issuer_url", "Issuer"], ["sso_client_id", "Client ID"]];
  const missing = required.filter(([key]) => !valueOf(key)).map(([, label]) => label);
  readiness.classList.toggle("is-ready", missing.length === 0);
  readiness.innerHTML = missing.length
    ? `<strong>还差 ${missing.length} 项</strong><span>${missing.map(escapeHtml).join("、")}</span>`
    : "<strong>配置完整</strong><span>保存后即可发起企业登录</span>";
}

function applyOneAccessPreset() {
  const values = {
    sso_mode: "manual",
    sso_scopes: "get_user_info",
    sso_username_claim: "userName",
    sso_display_name_claim: "name",
    sso_group_claim: "groups",
  };
  Object.entries(values).forEach(([name, value]) => {
    const input = $(`#settingsForm [name="${name}"]`);
    if (input) input.value = value;
  });
  updateSsoModeFields();
  const persisted = $("#ssoPersistedState");
  if (persisted) {
    persisted.classList.remove("is-saved");
    persisted.innerHTML = "<strong>已应用 OneAccess 预设，尚未保存</strong><span>继续填写三个服务地址、Client ID、Secret 和回调地址</span>";
  }
  toast("已设置 Scope=get_user_info、工号=userName、姓名=name");
}

function closeSsoDiagnosticModal() {
  const modal = $("#ssoDiagnosticModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
  $("#ssoDiagnosticForm")?.reset();
}

function renderSsoDiagnosticResult(data) {
  const target = $("#ssoDiagnosticResult");
  if (!target) return;
  const statusLabel = {
    incomplete: "配置未完成",
    configured: "配置可用",
    mapping_failed: "字段映射失败",
    matched: "已匹配用户",
    will_create: "将自动创建",
  }[data.status] || "诊断结果";
  const rows = [
    ["状态", statusLabel],
    ["说明", data.message || ""],
    ["模式", data.mode === "manual" ? "手动 OAuth2 端点" : "OIDC 自动发现"],
    ["Scope", data.scopes || "未配置"],
    ["回调地址", data.redirect_uri || "未配置"],
  ];
  if (data.userinfo_checked) {
    rows.push(
      ["映射工号", data.employee_id || "未找到"],
      ["映射姓名", data.display_name || "未找到"],
      ["实际工号字段", data.username_claim_used || "未找到"],
      ["实际姓名字段", data.display_name_claim_used || "未找到"],
      ["现有账号", data.existing_user ? `${data.existing_user.display_name}（${data.existing_user.username}）` : "无"],
      ["建议团队", data.suggested_org?.path || data.suggested_org?.name || "未匹配"],
    );
  }
  target.innerHTML = `
    <div class="sso-diagnostic-status sso-diagnostic-${escapeHtml(data.status || "configured")}">
      <strong>${escapeHtml(statusLabel)}</strong>
      <span>${escapeHtml(data.message || "")}</span>
    </div>
    <dl class="sso-diagnostic-grid">
      ${rows.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("")}
    </dl>
    ${data.warnings?.length ? `<div class="sso-diagnostic-warnings">${data.warnings.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : ""}
    ${data.available_claims?.length ? `<div class="sso-claim-list"><strong>UserInfo 可用字段</strong><span>${data.available_claims.map((item) => `<code>${escapeHtml(item)}</code>`).join("")}</span></div>` : ""}
    ${data.groups?.length ? `<div class="sso-claim-list"><strong>群组值</strong><span>${data.groups.map((item) => `<code>${escapeHtml(item)}</code>`).join("")}</span></div>` : ""}`;
}

async function runSsoDiagnostic(accessToken = "") {
  const target = $("#ssoDiagnosticResult");
  if (target) target.innerHTML = '<p class="empty-note">正在连接已保存的 SSO 配置…</p>';
  const data = await api("/api/sso/diagnose", {
    method: "POST",
    body: JSON.stringify({ access_token: accessToken }),
  });
  renderSsoDiagnosticResult(data);
}

function openSsoDiagnosticModal() {
  const modal = $("#ssoDiagnosticModal");
  if (!modal) return;
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  runSsoDiagnostic().catch((error) => {
    const target = $("#ssoDiagnosticResult");
    if (target) target.innerHTML = `<div class="sso-diagnostic-status sso-diagnostic-mapping_failed"><strong>诊断失败</strong><span>${escapeHtml(error.message)}</span></div>`;
  });
}

function renderBackups() {
  const list = $("#backupList");
  if (!list) return;
  list.innerHTML = state.backups.length ? `
    <table class="backup-table">
      <thead><tr><th>文件</th><th>类型</th><th>大小</th><th>创建时间</th><th>校验 / 恢复</th><th>操作</th></tr></thead>
      <tbody>
        ${state.backups.map((backup) => `
          <tr>
            <td>${escapeHtml(backup.filename)}</td>
            <td>${backup.kind === "auto" ? "自动" : "手动"}</td>
            <td>${formatBytes(backup.size_bytes)}</td>
            <td><strong>${escapeHtml(shortDateTime(backup.created_at || ""))}</strong><small>${escapeHtml(backup.creator || "系统")}</small></td>
            <td>
              <div class="backup-status">
                <span class="pill ${backup.verify_status === "ok" ? "status-done" : backup.verify_status === "failed" ? "status-risk" : ""}">${backup.verify_status === "ok" ? "已校验" : backup.verify_status === "failed" ? "校验失败" : "未校验"}</span>
                ${backup.verified_at ? `<small>${escapeHtml(shortDateTime(backup.verified_at))}</small>` : ""}
                ${backup.verify_message ? `<small>${escapeHtml(backup.verify_message)}</small>` : ""}
                ${backup.restored_at ? `<small class="restore-note">已恢复：${escapeHtml(shortDateTime(backup.restored_at))}</small>` : ""}
              </div>
            </td>
            <td>
              <div class="backup-actions">
                <a class="link-url" href="/api/backups/download?file=${encodeURIComponent(backup.filename)}">下载</a>
                <button class="secondary backup-verify-btn" type="button" data-backup-file="${escapeHtml(backup.filename)}">校验</button>
                <button class="danger backup-restore-btn" type="button" data-backup-file="${escapeHtml(backup.filename)}">恢复</button>
              </div>
            </td>
          </tr>`).join("")}
      </tbody>
    </table>` : "<p>暂无备份</p>";
}

function renderArchiveYears() {
  const list = $("#archiveYearList");
  const yearFilter = $("#archiveYearFilter");
  if (yearFilter) {
    const current = yearFilter.value;
    yearFilter.innerHTML = `<option value="">全部年份</option>${state.archiveYears.map((item) => `<option value="${escapeHtml(item.year)}">${escapeHtml(item.year)} 年</option>`).join("")}`;
    yearFilter.value = current;
  }
  if (!list) return;
  list.innerHTML = state.archiveYears.length ? state.archiveYears.map((item) => {
    const types = Object.values(item.types || {});
    return `<button class="archive-year-card" type="button" data-archive-year="${escapeHtml(item.year)}">
      <strong>${escapeHtml(item.year)}</strong>
      <span>${Number(item.total || 0)} 条记录</span>
      <small>${types.map((type) => `${escapeHtml(type.label)} ${Number(type.count || 0)}`).join(" · ")}</small>
    </button>`;
  }).join("") : `<p class="empty-note">暂无可归档数据</p>`;
}

function renderArchiveResults() {
  const list = $("#archiveSearchResults");
  const summary = $("#archiveSearchSummary");
  if (summary) {
    summary.textContent = state.archiveResults.length ? `共找到 ${state.archiveResults.length} 条结果` : "输入关键词或选择年份后搜索";
  }
  if (!list) return;
  list.innerHTML = state.archiveResults.length ? state.archiveResults.map((item) => `
    <article class="archive-result-item">
      <div class="archive-result-meta">
        <span class="pill">${escapeHtml(item.type_label || item.type)}</span>
        <span>${escapeHtml(shortDate(item.date || ""))}</span>
        ${item.owner ? `<span>${escapeHtml(item.owner)}</span>` : ""}
      </div>
      <h3>${escapeHtml(item.title || "未命名内容")}</h3>
      ${item.body ? `<p>${escapeHtml(item.body)}</p>` : ""}
    </article>
  `).join("") : `<p class="empty-note">暂无搜索结果</p>`;
}

async function loadArchive() {
  const data = await api("/api/archive/years");
  state.archiveYears = data.years || [];
  renderArchiveYears();
  renderArchiveResults();
}

async function searchArchive(form) {
  const params = new URLSearchParams(fullFormData(form));
  const data = await api(`/api/archive/search?${params.toString()}`);
  state.archiveResults = data.results || [];
  renderArchiveResults();
}

function renderAuditLogs() {
  const list = $("#auditLogList");
  if (!list) return;
  list.innerHTML = state.auditLogs.length ? `
    <table>
      <thead><tr><th>时间</th><th>操作人</th><th>动作</th><th>对象</th><th>摘要</th></tr></thead>
      <tbody>
        ${state.auditLogs.map((log) => `
          <tr>
            <td>${escapeHtml(log.created_at)}</td>
            <td>${escapeHtml(log.actor || "系统")}</td>
            <td><span class="pill">${escapeHtml(log.action)}</span></td>
            <td>${escapeHtml(log.entity_type)}${log.entity_id ? ` #${escapeHtml(log.entity_id)}` : ""}</td>
            <td>${escapeHtml(log.summary || "")}</td>
          </tr>`).join("")}
      </tbody>
    </table>` : "<p>暂无审计日志</p>";
}

function applySettingDefaults() {
  const shiftHours = $('input[name="hours"]');
  if (shiftHours && !shiftHours.value) shiftHours.value = settingValue("shift_default_hours", "12");
  const thankEvidence = $('textarea[name="evidence"]');
  if (thankEvidence) thankEvidence.placeholder = `写下对方帮助你的具体事实。本周最多感谢 ${settingValue("thank_you_weekly_limit", "3")} 人。`;
  const scorePoints = $('input[name="points"]');
  if (scorePoints && !scorePoints.value) scorePoints.value = settingValue("red_score_default_points", "1");
}

function scoreRuleLabel(rule) {
  if (!rule) return "未关联规则";
  const sameKindRules = state.rules.filter((item) => item.kind === rule.kind);
  const index = sameKindRules.findIndex((item) => Number(item.id) === Number(rule.id)) + 1;
  return `${rule.kind === "red" ? "红榜" : "黑榜"} #${index || "-"} · ${rule.content}`;
}

function renderSelectedScoreRule() {
  const form = $("#scoreForm");
  const target = $("#selectedScoreRule");
  if (!form || !target) return;
  const ruleId = form.elements.rule_id?.value;
  const rule = state.rules.find((item) => Number(item.id) === Number(ruleId));
  target.innerHTML = rule
    ? `<strong>${escapeHtml(scoreRuleLabel(rule))}</strong><button class="secondary clear-score-rule-btn" type="button">清除</button>`
    : `<span>从下方红黑榜细则中勾选规则</span>`;
  $$(".rule-pick-btn").forEach((button) => {
    button.classList.toggle("selected", Number(button.dataset.ruleId) === Number(ruleId));
  });
}

function selectScoreRule(ruleId) {
  const form = $("#scoreForm");
  const rule = state.rules.find((item) => Number(item.id) === Number(ruleId));
  if (!form || !rule) return;
  form.elements.rule_id.value = rule.id;
  form.elements.kind.value = rule.kind;
  if (!form.elements.points.value) {
    form.elements.points.value = settingValue(rule.kind === "red" ? "red_score_default_points" : "black_score_default_points", "1");
  }
  renderSelectedScoreRule();
}

function renderRuleSelectOptions(selectedId = "") {
  return `<option value="">不关联规则</option>${state.rules.map((rule) => {
    const label = scoreRuleLabel(rule);
    return `<option value="${rule.id}" ${Number(selectedId) === Number(rule.id) ? "selected" : ""}>${escapeHtml(label)}</option>`;
  }).join("")}`;
}

function renderScoreList(scores) {
  const list = $("#scoreList");
  if (!list) return;
  const visibleScores = isAdminView() || settingEnabled("red_black_show_black_details")
    ? scores
    : scores.filter((score) => score.kind !== "black");
  if (!visibleScores.length) {
    list.innerHTML = "<p>暂无积分记录</p>";
    return;
  }
  list.innerHTML = `
    <table>
      <thead><tr><th>日期</th><th>成员</th><th>类型</th><th>积分</th><th>规则</th><th>依据</th><th>操作</th></tr></thead>
      <tbody>
        ${visibleScores.map((score) => {
          const editable = isAdminView() && score.score_date === iso(new Date());
          if (!editable) {
            return `<tr>
              <td>${escapeHtml(score.score_date)}</td>
              <td><button class="score-member-link" type="button" data-score-user-id="${score.user_id}" data-score-user-name="${escapeHtml(score.display_name)}">${escapeHtml(score.display_name)}</button></td>
              <td>${score.kind === "red" ? "红榜" : "黑榜"}</td>
              <td>${escapeHtml(score.points)}</td>
              <td>${escapeHtml(score.rule_title || "-")}</td>
              <td>${escapeHtml(score.reason)}</td>
              <td><span class="pill">只读</span></td>
            </tr>`;
          }
          return `<tr>
            <td><input form="scoreEdit${score.id}" name="score_date" type="date" value="${escapeHtml(score.score_date)}"></td>
            <td><select form="scoreEdit${score.id}" name="user_id">${renderUserOptions(score.user_id, "成员", state.ruleUsers)}</select></td>
            <td><select form="scoreEdit${score.id}" name="kind"><option value="red" ${score.kind === "red" ? "selected" : ""}>红榜</option><option value="black" ${score.kind === "black" ? "selected" : ""}>黑榜</option></select></td>
            <td><input form="scoreEdit${score.id}" name="points" type="number" min="1" value="${Math.abs(Number(score.points || 0))}"></td>
            <td><select form="scoreEdit${score.id}" name="rule_id">${renderRuleSelectOptions(score.rule_id)}</select></td>
            <td><input form="scoreEdit${score.id}" name="reason" value="${escapeHtml(score.reason || "")}"></td>
            <td>
              <form id="scoreEdit${score.id}" class="score-edit-form" data-score-id="${score.id}">
                <button type="submit">保存</button>
              </form>
            </td>
          </tr>`;
        }).join("")}
      </tbody>
    </table>`;
}

function closeMemberScoreModal() {
  const modal = $("#memberScoreModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
}

async function openMemberScoreModal(userId, displayName) {
  const modal = $("#memberScoreModal");
  const list = $("#memberScoreList");
  if (!modal || !list) return;
  $("#memberScoreTitle").textContent = `${displayName || "成员"}的红黑榜`;
  $("#memberScoreSubtitle").textContent = "按时间倒序展示全部历史积分记录。";
  list.innerHTML = '<p class="empty-note">正在加载...</p>';
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  try {
    const data = await api(`/api/scores?user_id=${encodeURIComponent(userId)}`);
    const records = (data.scores || []).filter((score) => isAdminView()
      || settingEnabled("red_black_show_black_details")
      || score.kind !== "black");
    const redTotal = records.filter((score) => score.kind === "red").reduce((sum, score) => sum + Math.abs(Number(score.points || 0)), 0);
    const blackTotal = records.filter((score) => score.kind === "black").reduce((sum, score) => sum + Math.abs(Number(score.points || 0)), 0);
    const showBlack = isAdminView() || settingEnabled("red_black_show_black_points");
    $("#memberScoreSummary").innerHTML = `
      <span class="member-score-total red"><small>红榜累计</small><strong>${redTotal}</strong></span>
      ${showBlack ? `<span class="member-score-total black"><small>黑榜累计</small><strong>${blackTotal}</strong></span>` : ""}
      <span class="member-score-total"><small>记录数</small><strong>${records.length}</strong></span>`;
    list.innerHTML = records.length ? records.map((score) => `
      <article class="member-score-record ${score.kind}">
        <div><span class="pill ${score.kind}">${score.kind === "red" ? "红榜" : "黑榜"}</span><strong>${Math.abs(Number(score.points || 0))} 分</strong><time>${escapeHtml(score.score_date)}</time></div>
        <h3>${escapeHtml(score.rule_title || "未关联细则")}</h3>
        <p>${escapeHtml(score.reason || "未填写事实依据")}</p>
      </article>`).join("") : '<p class="empty-note">暂无相关积分记录。</p>';
  } catch (error) {
    list.innerHTML = `<p class="empty-note">${escapeHtml(error.message)}</p>`;
  }
}

function scoreYearValue() {
  const input = $("#scoreYear");
  const fallback = new Date().getFullYear();
  const value = Number(input?.value || fallback);
  const year = Number.isFinite(value) && value >= 2000 && value <= 2100 ? value : fallback;
  if (input) input.value = String(year);
  return year;
}

function scoreClass(value) {
  const number = Number(value || 0);
  if (number > 0) return "positive";
  if (number < 0) return "negative";
  return "zero";
}

function renderAnnualScoreTable(rows = [], year = new Date().getFullYear(), showBlack = true) {
  const target = $("#annualScoreTable");
  if (!target) return;
  const months = Array.from({ length: 12 }, (_, index) => index + 1);
  if (!rows.length) {
    target.innerHTML = `<p class="empty-note">${year} 年暂无积分数据。</p>`;
    return;
  }
  const maxMonthly = Math.max(1, ...rows.flatMap((row) => Object.values(row.months || {}).flatMap((value) => showBlack
    ? [Number(value.red || 0), Number(value.black || 0)]
    : [Number(value.red || 0)])));
  target.innerHTML = `
    <div class="annual-score-legend">
      <span class="annual-legend-item red"><i></i>红榜积分</span>
      ${showBlack ? '<span class="annual-legend-item black"><i></i>黑榜积分</span>' : ""}
      <small>按年度红榜积分从高到低排列${showBlack ? "，红黑榜不相互抵扣" : ""}；点击成员查看历史</small>
    </div>
    <table class="annual-score-table">
      <thead>
        <tr>
          <th class="member-col">成员</th>
          ${months.map((month) => `<th>${month}月</th>`).join("")}
          <th class="total-col">年度累计</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map((row, rowIndex) => {
          const monthsData = row.months || {};
          return `<tr>
            <th class="member-col"><button class="annual-member-cell annual-member-button" type="button" data-score-user-id="${row.id}" data-score-user-name="${escapeHtml(row.display_name || "未命名")}"><span class="annual-member-rank">${rowIndex + 1}</span><span>${escapeHtml(row.display_name || "未命名")}</span></button></th>
            ${months.map((month) => {
              const value = monthsData[String(month)] || {};
              const red = Number(value.red || 0);
              const black = Number(value.black || 0);
              if (!red && (!showBlack || !black)) return `<td><span class="annual-score-empty">—</span></td>`;
              const redStrength = 0.55 + Math.min(1, red / maxMonthly) * 0.35;
              const blackStrength = 0.55 + Math.min(1, black / maxMonthly) * 0.35;
              return `<td><div class="annual-month-score">
                ${red ? `<span class="score-red" style="--score-strength:${redStrength}"><b>红</b>${red}</span>` : ""}
                ${showBlack && black ? `<span class="score-black" style="--score-strength:${blackStrength}"><b>黑</b>${black}</span>` : ""}
              </div></td>`;
            }).join("")}
            <td class="total-col"><div class="annual-total-score"><span class="score-red"><b>红榜</b>${Number(row.total_red || 0)}</span>${showBlack ? `<span class="score-black"><b>黑榜</b>${Number(row.total_black || 0)}</span>` : ""}</div></td>
          </tr>`;
        }).join("")}
      </tbody>
    </table>`;
}

async function loadRulesAndScores() {
  state.rules = (await api("/api/rules")).rules;
  const year = scoreYearValue();
  const [scoresData, annualData] = await Promise.all([
    api(`/api/scores?${periodQuery()}`),
    api(`/api/dashboards/red-black?from=${year}-01-01&to=${year}-12-31`),
  ]);
  const scores = scoresData.scores || [];
  state.ruleUsers = (annualData.annual || []).map((user) => ({ ...user, active: 1 }));
  const renderRuleColumn = (kind, title) => {
    const rules = state.rules.filter((rule) => rule.kind === kind);
    return `<section class="rule-column ${kind}">
      <div class="rule-column-head">
        <span class="pill ${kind}">${title}</span>
        <small>${rules.length} 条</small>
      </div>
      <div class="item-list">
        ${rules.length ? rules.map((rule, index) => `
          <button class="item rule-pick-btn" type="button" data-rule-id="${rule.id}" data-rule-kind="${rule.kind}" data-rule-index="${index + 1}">
            <span class="rule-number">${index + 1}</span>
            <p>${escapeHtml(rule.content)}</p>
          </button>`).join("") : "<p>暂无规则</p>"}
      </div>
    </section>`;
  };
  $("#ruleList").innerHTML = renderRuleColumn("red", "红榜") + renderRuleColumn("black", "黑榜");
  const showBlackPoints = isAdminView() || settingEnabled("red_black_show_black_points");
  renderAnnualScoreTable(annualData.annual || [], year, showBlackPoints);
  renderScoreList(scores);
  const visibilityForm = $("#blackVisibilityForm");
  if (visibilityForm) {
    visibilityForm.elements.show_points.checked = settingEnabled("red_black_show_black_points");
    visibilityForm.elements.show_details.checked = settingEnabled("red_black_show_black_details");
  }
  populateSelects();
  renderSelectedScoreRule();
}

function recurrenceRule(option = {}) {
  const type = option.recurrence_type || "weekly";
  const value = option.recurrence_value || option.recurrence_weeks || "1";
  return `${type}:${value}`;
}

function recurrenceOptions(selected = "weekly:1") {
  const options = [
    ["weekly:1", "每 1 周"],
    ["weekly:2", "每 2 周"],
    ["weekly:3", "每 3 周"],
    ["weekly:4", "每 4 周"],
    ["monthly_week:first", "每月第 1 周"],
    ["monthly_week:second", "每月第 2 周"],
    ["monthly_week:third", "每月第 3 周"],
    ["monthly_week:fourth", "每月第 4 周"],
    ["monthly_week:penultimate", "每月倒数第 2 周"],
    ["monthly_week:last", "每月最后 1 周"],
  ];
  return options.map(([value, label]) => `<option value="${value}" ${selected === value ? "selected" : ""}>${label}</option>`).join("");
}

function renderPresetTypeOptions(selectedId) {
  return state.topics.map((topic) => `<option value="${topic.id}" ${Number(selectedId) === Number(topic.id) ? "selected" : ""}>${escapeHtml(topic.name)}</option>`).join("");
}

function meetingTopicTypes(meeting) {
  return meeting?.topic_types || [];
}

function topicOptionsForMeeting(meeting, selectedId = null) {
  const topics = meetingTopicTypes(meeting);
  return topics.map((topic) => `<option value="${topic.id}" ${Number(selectedId) === Number(topic.id) ? "selected" : ""}>${escapeHtml(topic.name)}</option>`).join("");
}

function renderUserOptions(selectedId, placeholder = "负责人", users = state.users) {
  const options = users
    .filter((user) => user.active !== 0)
    .map((user) => {
      const label = user.org_unit_name ? `${user.display_name} · ${user.org_unit_name}` : user.display_name;
      return `<option value="${user.id}" ${Number(selectedId) === Number(user.id) ? "selected" : ""}>${escapeHtml(label)}</option>`;
    })
    .join("");
  return `<option value="">${placeholder}</option>${options}`;
}

function renderTopicPresetList() {
  const list = $("#topicPresetList");
  if (!list) return;
  const groups = state.topics.filter((topic) => (topic.options || []).length);
  list.innerHTML = groups.length ? `<div class="preset-library">
    ${groups.map((topic, index) => `<details class="preset-primary-group" ${index === 0 ? "open" : ""}>
      <summary><span><span class="topic-dot" style="background:${escapeHtml(topic.color)}"></span><strong>${escapeHtml(topic.name)}</strong></span><span>${topic.options.length} 个二级议题</span></summary>
      <div class="preset-secondary-list">
        ${topic.options.map((option) => `<form class="preset-row preset-form" data-option-id="${option.id}">
          <div class="preset-row-main">
            <input name="title" value="${escapeHtml(option.title)}" placeholder="二级议题名称" required>
            <select name="owner_id">${renderUserOptions(option.owner_id, "默认负责人", state.coordinationUsers)}</select>
            <select name="recurrence_rule">${recurrenceOptions(recurrenceRule(option))}</select>
            <span>${Number(option.duration_minutes || 10)} 分钟</span>
            <button>保存</button>
            <button class="danger preset-delete-btn" type="button" data-option-id="${option.id}">删除</button>
          </div>
          <details class="preset-row-advanced">
            <summary>更多设置</summary>
            <div>
              <label>一级分类<select name="type_id">${renderPresetTypeOptions(option.type_id)}</select></label>
              <label>预计时长<input name="duration_minutes" type="number" min="1" max="180" value="${Number(option.duration_minutes || 10)}"></label>
              <label>期望产出<input name="expected_output" value="${escapeHtml(option.expected_output || "")}" placeholder="例如：形成结论"></label>
              <label>会前材料<input name="materials" value="${escapeHtml(option.materials || "")}" placeholder="文档、数据或链接"></label>
              <label class="preset-detail-field">默认说明<textarea name="default_detail" placeholder="议题背景或讨论要求">${escapeHtml(option.default_detail || "")}</textarea></label>
            </div>
          </details>
        </form>`).join("")}
      </div>
    </details>`).join("")}
  </div>` : "<p>暂无二级预设议题，请先新增一级分类。</p>";
}

function renderPresetTopicForm(meeting) {
  const topics = meetingTopicTypes(meeting);
  const firstTopic = topics[0];
  const sourceTopic = state.topics.find((topic) => Number(topic.id) === Number(firstTopic?.id));
  const options = sourceTopic?.options || [];
  if (!topics.length) return "<p>请先在本场会议主题里选择至少一个主题。</p>";
  return `
    <form class="form-grid compact topic-item-form" data-meeting-id="${meeting.id}">
      <select name="type_id" data-meeting-topic-select required>${topicOptionsForMeeting(meeting)}</select>
      <select name="option_id" data-meeting-option-select><option value="">自定义议题</option>${options.map((option) => `<option value="${option.id}">${escapeHtml(option.title)}</option>`).join("")}</select>
      <input name="title" placeholder="自定义标题，选择预设时可留空" />
      <select name="owner_id">${renderUserOptions(null, "负责人", state.coordinationUsers)}</select>
      <input name="duration_minutes" type="number" min="1" max="180" value="10" title="预计时长（分钟）" />
      <input name="expected_output" placeholder="期望产出，例如形成结论" />
      <input name="materials" placeholder="会前材料、数据或链接" />
      <input name="due_date" type="date" />
      <textarea name="detail" placeholder="议题说明、背景、结论或行动要求"></textarea>
      <button>添加到本次例会</button>
    </form>`;
}

function renderCustomTopicForm(meeting) {
  if (!canOperate("meetings", "create")) return '<p class="empty-note">当前用户类型仅可查看会议议题。</p>';
  const topics = meetingTopicTypes(meeting);
  if (!topics.length) return "<p>本场会议尚未设置主题，暂不能添加议题。</p>";
  return `
    <form class="form-grid compact topic-item-form custom-topic-form" data-meeting-id="${meeting.id}">
      <select name="type_id" required>${topicOptionsForMeeting(meeting)}</select>
      <input name="title" placeholder="自定义议题标题" required />
      <select name="owner_id">${renderUserOptions(null, "负责人", state.coordinationUsers)}</select>
      <input name="duration_minutes" type="number" min="1" max="180" value="10" title="预计时长（分钟）" />
      <input name="expected_output" placeholder="期望产出，例如同步信息" />
      <input name="materials" placeholder="会前材料、数据或链接" />
      <textarea name="detail" placeholder="补充议题背景、希望讨论的问题或建议结论"></textarea>
      <button>提交自定义议题</button>
    </form>`;
}

function renderMeetingMinuteSummary(item) {
  const [statusLabel, statusClass] = meetingItemStatusMeta[item.status] || meetingItemStatusMeta.todo;
  const hasMinuteContent = Boolean(item.minutes || item.open_issues || item.next_steps);
  return `
    <div class="minute-summary ${hasMinuteContent ? "" : "is-empty"}">
      <div class="minute-summary-head">
        <span class="morning-badge ${statusClass}">${escapeHtml(statusLabel)}</span>
        <span>${hasMinuteContent ? "已记录纪要" : "待记录纪要"}</span>
      </div>
      ${item.minutes ? `<p><strong>纪要：</strong>${escapeHtml(item.minutes)}</p>` : `<p>暂无纪要，点击按钮记录本议题讨论结论。</p>`}
      ${item.open_issues ? `<p><strong>遗留：</strong>${escapeHtml(item.open_issues)}</p>` : ""}
      ${item.next_steps ? `<p><strong>下一步：</strong>${escapeHtml(item.next_steps)}</p>` : ""}
    </div>`;
}

function renderMeetingItem(item, meeting) {
  const meta = [
    item.owner_name || "",
    item.created_by_name ? `提交：${item.created_by_name}` : "",
    item.due_date ? `截止：${item.due_date}` : "",
  ].filter(Boolean).join(" · ");
  const thankYouTopic = isThankYouTopic(item);
  const inherited = Boolean(meeting.inherited);
  const locked = meetingIsLocked(meeting) || inherited;
  const prepared = Boolean(item.materials);
  return `<article class="topic-item meeting-agenda-item ${locked ? "is-locked" : ""}" style="--agenda-color:${escapeHtml(item.type_color || "#64748b")}" data-meeting-item-id="${item.id}" draggable="${!locked && canOperate("meetings", "edit") ? "true" : "false"}">
    <div class="agenda-item-head">
      <span class="agenda-drag-handle" title="拖动调整顺序" aria-hidden="true">⋮⋮</span>
      <div class="agenda-item-title">
        <span class="agenda-type-badge" style="--agenda-color:${escapeHtml(item.type_color || "#64748b")}">${escapeHtml(item.type_name || item.section || "议题")}</span>
        <strong>${escapeHtml(item.title)}</strong>${item.carried_from_id ? `<span class="agenda-source-badge">上场顺延</span>` : ""}
      </div>
      <span class="agenda-duration">${Number(item.duration_minutes || 10)} 分钟</span>
    </div>
    ${item.detail ? `<p>${escapeHtml(item.detail)}</p>` : ""}
    ${meta ? `<small>${escapeHtml(meta)}</small>` : ""}
    <div class="agenda-prep-grid">
      <div><span>期望产出</span><strong>${escapeHtml(item.expected_output || "待补充")}</strong></div>
      <div class="${prepared ? "is-ready" : "is-missing"}"><span>会前材料</span><strong>${escapeHtml(item.materials || "待准备")}</strong></div>
    </div>
    ${thankYouTopic ? `
      <div class="topic-auto-summary">
        Thank You 议题将由系统自动汇总本周点赞记录，无需单独填写会议纪要。
      </div>` : renderMeetingMinuteSummary(item)}
    ${locked ? `<div class="agenda-locked-note">${inherited ? `上级团队 ${escapeHtml(meeting.org_unit_name || "")} 安排，当前团队只读` : "会议已结束，内容只读"}</div>` : (canOperate("meetings", "edit") || canOperate("meetings", "delete")) ? `
      <div class="topic-item-actions agenda-actions">
        ${!thankYouTopic && canOperate("meetings", "edit") ? `
          <button class="meeting-quick-note-btn" type="button" data-item-id="${item.id}" data-note-mode="decision">记结论</button>
          <button class="secondary meeting-quick-note-btn" type="button" data-item-id="${item.id}" data-note-mode="risk">记风险</button>
          <button class="secondary meeting-quick-note-btn" type="button" data-item-id="${item.id}" data-note-mode="confirm">待确认</button>
          <button class="secondary meeting-minute-btn" type="button" data-item-id="${item.id}">${item.minutes || item.open_issues || item.next_steps ? "完整编辑" : "记录纪要"}</button>
          <button class="secondary meeting-carry-btn" type="button" data-item-id="${item.id}">顺延</button>` : ""}
        ${canOperate("meetings", "delete") ? `<button class="danger meeting-item-delete-btn" type="button" data-item-id="${item.id}" data-item-title="${escapeHtml(item.title)}">删除</button>` : ""}
      </div>` : ""}
  </article>`;
}

function findMeetingItemContext(itemId) {
  for (const meeting of state.meetings) {
    const item = (meeting.items || []).find((entry) => Number(entry.id) === Number(itemId));
    if (item) return { meeting, item };
  }
  return { meeting: null, item: null };
}

function closeMeetingMinuteModal() {
  const modal = $("#meetingMinuteModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

function openMeetingMinuteModal(itemId, mode = "minutes") {
  const { meeting, item } = findMeetingItemContext(itemId);
  const modal = $("#meetingMinuteModal");
  const form = $("#meetingMinuteForm");
  if (!meeting || !item || !modal || !form) return;
  form.dataset.itemId = item.id;
  form.dataset.meetingId = meeting.id;
  form.reset();
  form.elements.owner_id.innerHTML = renderUserOptions(item.owner_id, "负责人", state.coordinationUsers);
  form.elements.owner_id.value = item.owner_id ? String(item.owner_id) : "";
  form.elements.status.innerHTML = renderMeetingItemStatusOptions(item.status || "todo");
  form.elements.status.value = item.status || "todo";
  form.elements.due_date.value = item.due_date || "";
  form.elements.duration_minutes.value = Number(item.duration_minutes || 10);
  form.elements.expected_output.value = item.expected_output || "";
  form.elements.materials.value = item.materials || "";
  form.elements.minutes.value = item.minutes || "";
  form.elements.open_issues.value = item.open_issues || "";
  form.elements.next_steps.value = item.next_steps || "";
  $("#meetingMinuteTitle").textContent = item.minutes || item.open_issues || item.next_steps ? "编辑会议纪要" : "记录会议纪要";
  $("#meetingMinuteSubtitle").textContent = `${meetingScheduleLabel(meeting)} · ${meeting.title}`;
  $("#meetingMinuteContext").innerHTML = `
    <h3>${escapeHtml(item.title)}</h3>
    <p>${escapeHtml(item.detail || "暂无议题说明")}</p>
    <div class="chip-list">
      <span class="chip">${escapeHtml(item.type_name || item.section || "议题")}</span>
      ${item.owner_name ? `<span class="chip">责任人 ${escapeHtml(item.owner_name)}</span>` : ""}
      ${item.due_date ? `<span class="chip">截止 ${escapeHtml(shortDate(item.due_date))}</span>` : ""}
    </div>`;
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  const prefixes = { risk: "【风险】", confirm: "【待确认】", decision: "【结论】" };
  if (prefixes[mode] && !form.elements.minutes.value.includes(prefixes[mode])) {
    form.elements.minutes.value = `${form.elements.minutes.value ? `${form.elements.minutes.value}\n` : ""}${prefixes[mode]}`;
  }
  form.elements.minutes.focus();
  form.elements.minutes.setSelectionRange(form.elements.minutes.value.length, form.elements.minutes.value.length);
}

function closeMeetingAgendaModal() {
  const modal = $("#meetingAgendaModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

function updateMeetingAgendaSelection() {
  const form = $("#meetingAgendaPickerForm");
  if (!form) return;
  const checked = $$(".meeting-agenda-option-check:checked", form);
  $$(".meeting-agenda-option", form).forEach((row) => {
    const selected = Boolean($(".meeting-agenda-option-check", row)?.checked);
    row.classList.toggle("selected", selected);
    const owner = $(".meeting-agenda-owner", row);
    if (owner) owner.disabled = !selected;
  });
  $$(".meeting-agenda-group", form).forEach((group) => {
    const options = $$(".meeting-agenda-option-check:not(:disabled)", group);
    const selected = options.filter((input) => input.checked);
    const toggle = $(".meeting-agenda-group-check", group);
    if (toggle) {
      toggle.checked = Boolean(options.length) && selected.length === options.length;
      toggle.indeterminate = selected.length > 0 && selected.length < options.length;
    }
  });
  $("#meetingAgendaSelectedCount").textContent = `已选 ${checked.length} 项`;
  $("#meetingAgendaSubmitBtn").disabled = checked.length === 0;
}

function renderMeetingAgendaPicker(meeting) {
  const list = $("#meetingAgendaPickerList");
  if (!list) return;
  const existing = new Set((meeting.items || []).map((item) => Number(item.option_id)).filter(Boolean));
  const groups = state.topics.filter((topic) => (topic.options || []).length);
  list.innerHTML = groups.length ? groups.map((topic, index) => {
    const total = (topic.options || []).length;
    const available = (topic.options || []).filter((option) => !existing.has(Number(option.id))).length;
    const added = total - available;
    return `<section class="meeting-agenda-group" data-search="${escapeHtml(`${topic.name} ${(topic.options || []).map((option) => option.title).join(" ")}`.toLowerCase())}">
      <div class="meeting-agenda-group-head">
        <label><input class="meeting-agenda-group-check" type="checkbox" ${available ? "" : "disabled"}><span class="topic-dot" style="background:${escapeHtml(topic.color)}"></span><strong>${escapeHtml(topic.name)}</strong></label>
        <span>${available} 项可选${added ? ` · ${added} 项已加入` : ""}</span>
      </div>
      <div class="meeting-agenda-group-options">
        ${(topic.options || []).map((option) => {
          const added = existing.has(Number(option.id));
          return `<div class="meeting-agenda-option ${added ? "already-added" : ""}" data-search="${escapeHtml(`${topic.name} ${option.title} ${option.default_detail || ""}`.toLowerCase())}">
            <label class="meeting-agenda-option-main">
              <input class="meeting-agenda-option-check" type="checkbox" value="${option.id}" ${added ? "disabled" : ""}>
              <span><strong>${escapeHtml(option.title)}</strong><small>${escapeHtml(option.default_detail || option.expected_output || "暂无补充说明")}</small></span>
            </label>
            <select class="meeting-agenda-owner" disabled aria-label="${escapeHtml(option.title)}责任人">${renderUserOptions(option.owner_id, "选择责任人", state.coordinationUsers)}</select>
            <span class="meeting-agenda-option-meta">${added ? "已加入" : `${Number(option.duration_minutes || 10)} 分钟`}</span>
          </div>`;
        }).join("")}
      </div>
    </section>`;
  }).join("") : `<div class="meeting-empty"><h3>暂无预设议题</h3><p>请先在会议管理中维护一级分类和二级预设议题。</p></div>`;
  updateMeetingAgendaSelection();
}

function openMeetingAgendaModal(meetingId) {
  const meeting = state.meetings.find((entry) => Number(entry.id) === Number(meetingId));
  const modal = $("#meetingAgendaModal");
  const form = $("#meetingAgendaPickerForm");
  if (!meeting || !modal || !form) return;
  form.reset();
  form.elements.meeting_id.value = meeting.id;
  $("#meetingAgendaSearch").value = "";
  $("#meetingAgendaSubtitle").textContent = `${meetingScheduleLabel(meeting)} · ${meeting.title} · 按一级分类批量勾选`;
  renderMeetingAgendaPicker(meeting);
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  $("#meetingAgendaSearch").focus();
}

function closeMeetingAttendanceModal() {
  const modal = $("#meetingAttendanceModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

function closeMeetingCreateModal() {
  const modal = $("#meetingCreateModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

function openMeetingCreateModal() {
  const modal = $("#meetingCreateModal");
  const form = $("#meetingCreateForm");
  if (!modal || !form) return;
  form.reset();
  form.elements.meeting_date.value = state.selectedMeetingDate || iso(new Date());
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  form.elements.title.focus();
}

async function createMeetingFromForm(form) {
  const response = await api("/api/meetings", { method: "POST", body: JSON.stringify(formData(form)) });
  state.meetings = response.meetings || state.meetings;
  state.selectedMeetingId = response.meeting_id;
  const created = state.meetings.find((meeting) => Number(meeting.id) === Number(response.meeting_id));
  if (created) state.selectedMeetingDate = created.meeting_date;
  form.reset();
  setDefaultDates();
  closeMeetingCreateModal();
  renderMeetingCalendar(state.meetings);
  renderMeetingList(state.meetings);
  renderMeetingDetail(created || null);
  openMeetingAgendaModal(response.meeting_id);
  toast("会议已创建，请勾选本场议题");
}

function closeMeetingEmailModal() {
  const modal = $("#meetingEmailModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

function openMeetingEmailModal(meetingId) {
  const meeting = state.meetings.find((entry) => Number(entry.id) === Number(meetingId));
  const modal = $("#meetingEmailModal");
  const form = $("#meetingEmailForm");
  if (!meeting || !modal || !form) return;
  form.reset();
  form.elements.meeting_id.value = meeting.id;
  form.elements.include_thanks.checked = true;
  $("#meetingEmailSubtitle").textContent = `${meetingScheduleLabel(meeting)} · ${meeting.title}`;
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}

function attendanceSummary(meeting) {
  const records = meeting.attendance || [];
  const count = (status) => records.filter((item) => item.status === status).length;
  const total = state.meetingUsers.filter((user) => user.active !== 0).length;
  return { total, signed: records.length, present: count("present"), late: count("late"), leave: count("leave"), absent: count("absent") };
}

function renderMeetingAttendanceSummary(meeting) {
  const summary = attendanceSummary(meeting);
  return `<div class="meeting-attendance-summary-grid">
    <span><strong>${summary.signed}/${summary.total}</strong>已签到</span>
    <span><strong>${summary.present}</strong>出席</span>
    <span><strong>${summary.late}</strong>迟到</span>
    <span><strong>${summary.leave}</strong>请假</span>
    <span><strong>${summary.absent}</strong>缺席</span>
  </div>`;
}

function openMeetingAttendanceModal(meetingId) {
  const meeting = state.meetings.find((entry) => Number(entry.id) === Number(meetingId));
  const modal = $("#meetingAttendanceModal");
  if (!meeting || !modal) return;
  const editable = isAdminView() && !meeting.inherited;
  $("#meetingAttendanceSubtitle").textContent = `${meetingScheduleLabel(meeting)} · ${meeting.title}${editable ? " · 点击即保存" : " · 只读"}`;
  $("#meetingAttendanceSummary").innerHTML = renderMeetingAttendanceSummary(meeting);
  $("#meetingAttendanceList").innerHTML = editable ? renderAttendance(meeting) : renderAttendanceReadonly(meeting);
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}

function renderTopicBoard(meeting) {
  if (!meetingTopicTypes(meeting).length && !meeting.items.length) {
    return `<div class="topic-board-empty">本场会议尚未设置主题。</div>`;
  }
  return meeting.items.length
    ? `<div class="meeting-agenda-list" data-meeting-agenda-list="${meeting.id}">${meeting.items.map((item) => renderMeetingItem(item, meeting)).join("")}</div>`
    : `<div class="topic-board-empty">主题已设置，暂时还没有议题。</div>`;
}

function renderAttendance(meeting) {
  const map = new Map((meeting.attendance || []).map((item) => [Number(item.user_id), item]));
  const attendanceUsers = state.meetingUsers;
  if (!attendanceUsers.length) return "<p>当前团队暂无成员账号</p>";
  const statuses = [
    ["present", "出席"],
    ["leave", "请假"],
    ["late", "迟到"],
    ["absent", "缺席"],
  ];
  return `<div class="attendance-grid">${attendanceUsers.filter((user) => user.active !== 0).map((user) => {
    const record = map.get(Number(user.id)) || {};
    const status = record.status || "present";
    const needsDonation = status === "late" || status === "absent";
    return `<form class="attendance-row" data-meeting-id="${meeting.id}">
      <strong>${escapeHtml(user.display_name)}</strong>
      <input type="hidden" name="user_id" value="${user.id}">
      <input type="hidden" name="status" value="${status}">
      <div class="attendance-status-group" role="group" aria-label="${escapeHtml(user.display_name)}签到状态">
        ${statuses.map(([value, label]) => `<button type="button" class="attendance-status-btn ${status === value ? "active" : ""} ${value}" data-attendance-status="${value}">${label}</button>`).join("")}
      </div>
      <div class="attendance-donation ${needsDonation ? "" : "hidden"}">
        <label>金额<input name="donation_amount" type="number" min="0" step="1" value="${Number(record.donation_amount || 0) || ""}" placeholder="乐捐金额"></label>
        <label class="donation-received"><input name="donation_done" type="checkbox" ${record.donation_done ? "checked" : ""}> 已收到</label>
      </div>
      <span class="attendance-save-state" aria-live="polite"></span>
    </form>`;
  }).join("")}</div>`;
}

function buildAttendanceDashboard(meetings = []) {
  const attendanceUsers = state.meetingUsers;
  const activeUsers = attendanceUsers.filter((user) => user.active !== 0);
  const totalMeetings = meetings.length;
  return activeUsers.map((user) => {
    const stats = {
      user,
      total: totalMeetings,
      present: 0,
      late: 0,
      leave: 0,
      absent: 0,
      unsigned: 0,
      donationRequired: 0,
      donationReceived: 0,
      donationPending: 0,
    };
    meetings.forEach((meeting) => {
      const record = (meeting.attendance || []).find((item) => Number(item.user_id) === Number(user.id));
      if (!record) {
        stats.unsigned += 1;
        return;
      }
      if (record.donation_required) {
        const amount = Number(record.donation_amount || 0);
        stats.donationRequired += amount;
        if (record.donation_done) {
          stats.donationReceived += amount;
        } else {
          stats.donationPending += amount;
        }
      }
      if (Object.prototype.hasOwnProperty.call(stats, record.status)) {
        stats[record.status] += 1;
      } else {
        stats.unsigned += 1;
      }
    });
    stats.attended = stats.present + stats.late;
    stats.rate = totalMeetings ? Math.round((stats.attended / totalMeetings) * 100) : 0;
    return stats;
  }).sort((a, b) => b.rate - a.rate || b.attended - a.attended || String(a.user.display_name).localeCompare(String(b.user.display_name), "zh-CN"));
}

function renderAttendanceDashboard(meetings = []) {
  const rows = buildAttendanceDashboard(meetings);
  if (!meetings.length) return "<p>本月暂无会议，暂不能统计出勤。</p>";
  if (!rows.length) return "<p>暂无成员账号。</p>";
  return `<div class="attendance-board">
    ${rows.map((row) => `
      <div class="attendance-board-row">
        <div class="attendance-person">
          <strong>${escapeHtml(row.user.display_name)}</strong>
          <span>${row.total} 场会议</span>
        </div>
        <div class="attendance-rate">
          <strong>${row.rate}%</strong>
          <span>出勤率</span>
        </div>
        <div class="attendance-bar" title="出席 ${row.present}，迟到 ${row.late}，请假 ${row.leave}，缺席 ${row.absent}，未签到 ${row.unsigned}">
          <span style="width:${row.total ? (row.present / row.total) * 100 : 0}%" class="present"></span>
          <span style="width:${row.total ? (row.late / row.total) * 100 : 0}%" class="late"></span>
          <span style="width:${row.total ? (row.leave / row.total) * 100 : 0}%" class="leave"></span>
          <span style="width:${row.total ? (row.absent / row.total) * 100 : 0}%" class="absent"></span>
          <span style="width:${row.total ? (row.unsigned / row.total) * 100 : 0}%" class="unsigned"></span>
        </div>
        <div class="attendance-counts">
          <span>出席 ${row.present}</span>
          <span>迟到 ${row.late}</span>
          <span>请假 ${row.leave}</span>
          <span>缺席 ${row.absent}</span>
          <span>未签到 ${row.unsigned}</span>
          <span class="${row.donationPending ? "warn" : ""}">乐捐 ${row.donationReceived}/${row.donationRequired}</span>
        </div>
      </div>`).join("")}
  </div>`;
}

function updateAttendanceDonationVisibility(form) {
  const status = form.elements.status?.value || "present";
  const needsDonation = status === "late" || status === "absent";
  const donation = form.querySelector(".attendance-donation");
  donation?.classList.toggle("hidden", !needsDonation);
  if (!needsDonation) {
    if (form.elements.donation_amount) form.elements.donation_amount.value = "";
    if (form.elements.donation_done) form.elements.donation_done.checked = false;
  }
}

function attendancePayload(form) {
  const status = form.elements.status?.value || "present";
  const needsDonation = status === "late" || status === "absent";
  return {
    user_id: form.elements.user_id.value,
    status,
    donation_amount: needsDonation ? form.elements.donation_amount?.value || 0 : 0,
    donation_done: needsDonation ? Boolean(form.elements.donation_done?.checked) : false,
  };
}

async function saveAttendanceForm(form) {
  const stateEl = form.querySelector(".attendance-save-state");
  if (stateEl) stateEl.textContent = "保存中";
  const response = await api(`/api/meetings/${form.dataset.meetingId}/attendance`, {
    method: "POST",
    body: JSON.stringify(attendancePayload(form)),
  });
  state.meetings = response.meetings || state.meetings;
  const current = state.meetings.find((meeting) => Number(meeting.id) === Number(state.selectedMeetingId));
  if (current) {
    renderMeetingList(state.meetings);
    renderMeetingDetail(current);
    if (!$("#meetingAttendanceModal")?.classList.contains("hidden")) {
      $("#meetingAttendanceSummary").innerHTML = renderMeetingAttendanceSummary(current);
    }
  }
  toast("签到已更新");
}

function meetingMinutesSubject(meeting) {
  return `【会议纪要】${meeting.meeting_date} ${meeting.title}`;
}

function meetingScheduleLabel(meeting, compact = false) {
  const date = compact ? shortDate(meeting.meeting_date) : meeting.meeting_date;
  return `${date}${meeting.start_time ? ` ${meeting.start_time}` : ""}`;
}

function tableCell(value, fallback = "无") {
  const text = String(value || fallback).trim() || fallback;
  return text.replace(/\|/g, "｜").replace(/\r?\n+/g, "；");
}

function groupAttendance(meeting) {
  const statusMap = { present: "出席", leave: "请假", absent: "缺席", late: "迟到" };
  const groups = { present: [], leave: [], absent: [], late: [] };
  (meeting.attendance || []).forEach((item) => {
    const key = groups[item.status] ? item.status : "present";
    groups[key].push(item.display_name);
  });
  return {
    present: groups.present.join("、") || "暂无签到记录",
    exceptions: ["leave", "absent", "late"]
      .filter((key) => groups[key].length)
      .map((key) => `${statusMap[key]}：${groups[key].join("、")}`)
      .join("；") || "无",
  };
}

function thankYouSummary(thankData = {}) {
  const votes = thankData.votes || [];
  const stars = thankData.stars || [];
  return {
    minutes: votes.length
      ? `本周共收到 ${votes.length} 条 Thank You，主要记录团队成员之间的具体协助事项。`
      : "本周暂无 Thank You 记录。",
    stars: stars.length
      ? stars.map((item) => `${item.display_name} ${Number(item.thanks || 0)} 次`).join("；")
      : "暂无",
    details: votes.length
      ? votes.map((vote, index) => `${index + 1}. ${vote.voter_name} 感谢 ${vote.receiver_name}：${vote.evidence}`).join("；")
      : "暂无明细",
  };
}

function markdownTable(rows) {
  return [
    "| 项目 | 内容 |",
    "|---|---|",
    ...rows.map(([label, value]) => `| ${tableCell(label)} | ${tableCell(value)} |`),
  ].join("\r\n");
}

function markdownMatrix(headers, rows) {
  return [
    `| ${headers.map((item) => tableCell(item)).join(" | ")} |`,
    `| ${headers.map(() => "---").join(" | ")} |`,
    ...rows.map((row) => `| ${row.map((item) => tableCell(item)).join(" | ")} |`),
  ].join("\r\n");
}

function meetingStatusLabel(status) {
  return meetingItemStatusMeta[status]?.[0] || "待处理";
}

function meetingMinuteRows(meeting, thankData = null) {
  const rows = (meeting.items || []).filter((item) => !isThankYouTopic(item)).map((item, index) => {
    const topicName = item.type_name || item.section || "议题";
    return [
      index + 1,
      topicName,
      item.title,
      item.minutes || "待补充",
      item.open_issues || "无",
      item.next_steps || "无",
      item.owner_name || "未指定",
      item.due_date || "无",
      meetingStatusLabel(item.status),
    ];
  });
  if (thankData) {
    const summary = thankYouSummary(thankData);
    rows.push([
      rows.length + 1,
      "Thank You",
      "本周 Thank You",
      summary.minutes,
      summary.stars,
      summary.details,
      "系统自动汇总",
      meeting.meeting_date,
      "已汇总",
    ]);
  }
  return rows;
}

function hasMeetingMinuteValue(value) {
  const text = String(value ?? "").trim();
  return Boolean(text) && !["无", "暂无", "未指定", "待补充", "暂无明细"].includes(text);
}

function meetingTopicTableRows(row) {
  const isThankYouRow = row[1] === "Thank You";
  const rows = isThankYouRow
    ? [
        ["议题类型", row[1], true],
        ["议题/事项", row[2], true],
        ["纪要/结论", row[3]],
        ["本周之星", row[4]],
        ["感谢明细", row[5]],
        ["来源", row[6]],
        ["统计日期", row[7]],
        ["状态", row[8]],
      ]
    : [
        ["议题类型", row[1], true],
        ["议题/事项", row[2], true],
        ["纪要/结论", row[3]],
        ["遗留问题", row[4]],
        ["下一步行动", row[5]],
        ["责任人", row[6]],
        ["完成时间", row[7]],
        ["状态", row[8]],
      ];
  return rows.filter(([, value, required]) => required || hasMeetingMinuteValue(value)).map(([label, value]) => [label, value]);
}

function buildMeetingMinutesText(meeting, thankData = null) {
  const attendance = groupAttendance(meeting);
  const rows = meetingMinuteRows(meeting, thankData);
  const pendingCount = meetingPendingCount(rows);
  const attendeeCount = meetingAttendanceCount(meeting);
  const lines = [
    meetingMinutesSubject(meeting),
    "",
    "战情概览",
    "",
    markdownTable([
      ["会议时间", meetingScheduleLabel(meeting)],
      ["与会人数", `${attendeeCount} 人`],
      ["待闭环", `${pendingCount} 项`],
      ["与会人", attendance.present],
      ["请假/缺席/迟到", attendance.exceptions],
      ["主持人", meeting.creator || "未记录"],
      ...(hasMeetingMinuteValue(meeting.summary) ? [["会议摘要", meeting.summary]] : []),
    ]),
    "",
    "一、按议题维度纪要与行动闭环",
    "",
  ];
  if (!rows.length) {
    lines.push("暂无议题。");
    return lines.join("\r\n");
  }
  rows.forEach((row) => {
    lines.push(`议题 ${row[0]}：${row[2]}`);
    lines.push("");
    lines.push(markdownTable(meetingTopicTableRows(row)));
    lines.push("");
  });
  lines.push("二、会后跟踪要求");
  lines.push("");
  lines.push("1. 请各责任人按完成时间推进闭环，逾期事项需在下次例会说明原因和调整计划。");
  lines.push("2. 遗留问题默认进入下次会议跟踪，已关闭事项需补充结论或证据。");
  lines.push("3. 本纪要以行动闭环为准，如内容有误请在当日内反馈修订。");
  return lines.join("\r\n");
}

function htmlCell(value, fallback = "无") {
  return escapeHtml(String(value || fallback).trim() || fallback).replace(/\r?\n/g, "<br>");
}

function htmlTable(rows) {
  return `<table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%;font-family:Arial,'Microsoft YaHei',sans-serif;font-size:14px;border-color:#d9dfe7;">
    <tbody>${rows.map(([label, value]) => `<tr><th style="width:130px;background:#f6f8fa;text-align:left;color:#172033;">${htmlCell(label)}</th><td>${htmlCell(value)}</td></tr>`).join("")}</tbody>
  </table>`;
}

function htmlMatrixTable(headers, rows) {
  return `<table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%;font-family:Arial,'Microsoft YaHei',sans-serif;font-size:13px;border-color:#d9dfe7;">
    <thead><tr>${headers.map((item) => `<th style="background:#eef3f8;color:#172033;text-align:left;">${htmlCell(item)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((row) => `<tr>${row.map((item, index) => `<td style="${index === 0 ? "text-align:center;" : ""}vertical-align:top;">${htmlCell(item)}</td>`).join("")}</tr>`).join("")}</tbody>
  </table>`;
}

function meetingAttendanceCount(meeting) {
  const present = (meeting.attendance || []).filter((item) => item.status === "present").length;
  if (present) return present;
  const names = groupAttendance(meeting).present;
  return names && names !== "暂无签到记录" ? names.split("、").filter(Boolean).length : 0;
}

function meetingPendingCount(rows) {
  return rows.filter((row) => !["已完成", "已汇总"].includes(row[8])).length;
}

function htmlTopicTable(rows) {
  return `<table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%;font-family:Arial,'Microsoft YaHei',sans-serif;font-size:14px;border-color:#d9dfe7;">
    <tbody>${rows.map(([label, value]) => {
      const warn = ["遗留问题", "风险"].includes(label);
      return `<tr>
        <th style="width:130px;background:${warn ? "#fff7f7" : "#eef3f8"};text-align:left;color:#172033;">${htmlCell(label)}</th>
        <td style="background:${warn ? "#fff7f7" : "#fff"};vertical-align:top;">${htmlCell(value)}</td>
      </tr>`;
    }).join("")}</tbody>
  </table>`;
}

function htmlTopicSections(rows) {
  return rows.map((row) => `
    <section style="margin:14px 0 16px;padding:14px;border:1px solid #d9dfe7;background:#fff;">
      <h3 style="margin:0 0 10px;font-size:15px;color:#172033;">
        <span style="display:inline-block;min-width:26px;height:26px;line-height:26px;text-align:center;border-radius:999px;background:#c7000b;color:#fff;margin-right:8px;font-weight:700;">${htmlCell(row[0])}</span>
        ${htmlCell(row[2])}
        <span style="display:inline-block;border:1px solid #d9dfe7;border-radius:999px;padding:2px 8px;margin-left:6px;font-size:12px;font-weight:400;background:#fff;">${htmlCell(row[1])}</span>
        ${hasMeetingMinuteValue(row[8]) ? `<span style="display:inline-block;border:1px solid #d9dfe7;border-radius:999px;padding:2px 8px;margin-left:4px;font-size:12px;font-weight:400;background:#fff;">${htmlCell(row[8])}</span>` : ""}
      </h3>
      ${htmlTopicTable(meetingTopicTableRows(row))}
    </section>
  `).join("");
}

function buildMeetingMinutesHtml(meeting, thankData = null) {
  const attendance = groupAttendance(meeting);
  const rows = meetingMinuteRows(meeting, thankData);
  const pendingCount = meetingPendingCount(rows);
  const attendeeCount = meetingAttendanceCount(meeting);
  return `<article style="font-family:Arial,'Microsoft YaHei',sans-serif;color:#172033;line-height:1.6;">
    <h1 style="margin:0 0 18px;font-size:22px;background:#fff7f7;border-top:4px solid #c7000b;padding:16px;">${htmlCell(meetingMinutesSubject(meeting))}</h1>
    ${hasMeetingMinuteValue(attendance.present) ? `<p style="margin:0 0 12px;color:#445066;">与会人：${htmlCell(attendance.present)}</p>` : ""}
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin:12px 0 18px;">
      <div style="border:1px solid #d9dfe7;background:#f8fafc;padding:14px;">
        <span style="display:block;color:#6b7280;font-size:12px;">会议时间</span>
        <strong style="display:block;margin-top:4px;color:#c7000b;font-size:23px;">${htmlCell(meetingScheduleLabel(meeting, true))}</strong>
      </div>
      <div style="border:1px solid #d9dfe7;background:#f8fafc;padding:14px;">
        <span style="display:block;color:#6b7280;font-size:12px;">与会人</span>
        <strong style="display:block;margin-top:4px;color:#c7000b;font-size:23px;">${attendeeCount} 人</strong>
      </div>
      <div style="border:1px solid #d9dfe7;background:#f8fafc;padding:14px;">
        <span style="display:block;color:#6b7280;font-size:12px;">待闭环</span>
        <strong style="display:block;margin-top:4px;color:#c7000b;font-size:23px;">${pendingCount} 项</strong>
      </div>
    </div>
    ${attendance.exceptions !== "无" || hasMeetingMinuteValue(meeting.summary) ? `
      <div style="border:1px solid #d9dfe7;background:#fff;padding:12px;margin:0 0 16px;">
        ${attendance.exceptions !== "无" ? `<p style="margin:0 0 6px;"><strong>请假/缺席/迟到：</strong>${htmlCell(attendance.exceptions)}</p>` : ""}
        ${hasMeetingMinuteValue(meeting.summary) ? `<p style="margin:0;"><strong>会议摘要：</strong>${htmlCell(meeting.summary)}</p>` : ""}
      </div>
    ` : ""}
    <h2 style="margin:18px 0 8px;font-size:17px;">一、按议题维度纪要与行动闭环</h2>
    ${rows.length ? htmlTopicSections(rows) : "<p>暂无议题。</p>"}
    <h2 style="margin:18px 0 8px;font-size:17px;">二、会后跟踪要求</h2>
    <ol style="margin-top:8px;padding-left:22px;">
      <li>请各责任人按完成时间推进闭环，逾期事项需在下次例会说明原因和调整计划。</li>
      <li>遗留问题默认进入下次会议跟踪，已关闭事项需补充结论或证据。</li>
      <li>本纪要以行动闭环为准，如内容有误请在当日内反馈修订。</li>
    </ol>
  </article>`;
}

function errorReason(error) {
  const name = error?.name ? `${error.name}` : "";
  const message = error?.message ? `${error.message}` : "";
  return [name, message].filter(Boolean).join("：") || "未知错误";
}

function copySelection(html, text, asHtml = true) {
  const element = document.createElement(asHtml ? "div" : "textarea");
  element.style.position = "fixed";
  element.style.left = "-9999px";
  element.style.top = "0";
  if (asHtml) {
    element.contentEditable = "true";
    element.innerHTML = html;
  } else {
    element.value = text;
  }
  document.body.appendChild(element);
  const selection = window.getSelection();
  try {
    if (asHtml) {
      const range = document.createRange();
      range.selectNodeContents(element);
      selection.removeAllRanges();
      selection.addRange(range);
    } else {
      element.focus();
      element.select();
    }
    if (!document.execCommand("copy")) {
      throw new Error("浏览器返回复制失败");
    }
    return { ok: true, method: asHtml ? "html-fallback" : "text-fallback" };
  } catch (error) {
    return { ok: false, reason: errorReason(error) };
  } finally {
    selection?.removeAllRanges();
    element.remove();
  }
}

async function copyMeetingMinutes(html, text) {
  const failures = [];
  if (navigator.clipboard) {
    try {
      if (window.ClipboardItem && navigator.clipboard.write) {
        await navigator.clipboard.write([new ClipboardItem({
          "text/html": new Blob([html], { type: "text/html" }),
          "text/plain": new Blob([text], { type: "text/plain" }),
        })]);
        return { ok: true, method: "html" };
      }
      await navigator.clipboard.writeText(text);
      return { ok: true, method: "text" };
    } catch (error) {
      failures.push(`剪贴板 API 失败：${errorReason(error)}`);
    }
  } else {
    failures.push("当前浏览器不支持 navigator.clipboard");
  }
  const htmlFallback = copySelection(html, text, true);
  if (htmlFallback.ok) return htmlFallback;
  failures.push(`兼容 HTML 复制失败：${htmlFallback.reason}`);
  const textFallback = copySelection("", text, false);
  if (textFallback.ok) return textFallback;
  failures.push(`兼容纯文本复制失败：${textFallback.reason}`);
  return { ok: false, reason: failures.join("；") };
}

function openMailDraft(subject) {
  const params = new URLSearchParams({ subject });
  const mailto = `mailto:?${params.toString()}`;
  const launcher = document.createElement("a");
  launcher.href = mailto;
  launcher.target = "_self";
  launcher.style.display = "none";
  launcher.setAttribute("aria-hidden", "true");
  try {
    document.body.appendChild(launcher);
    launcher.click();
    return { ok: true };
  } catch (error) {
    return { ok: false, reason: errorReason(error) };
  } finally {
    launcher.remove();
  }
}

async function openMeetingEmail(meetingId, includeThanks = true) {
  const meeting = state.meetings.find((item) => Number(item.id) === Number(meetingId));
  if (!meeting) throw new Error("生成会议邮件失败：请先选择会议");
  const weekStart = mondayOf(meeting.meeting_date);
  let thankData = null;
  if (includeThanks) {
    try {
      const [thankVotes, thankDashboard] = await Promise.all([
        api(`/api/thank-you?from=${encodeURIComponent(weekStart)}&to=${encodeURIComponent(weekStart)}`),
        api(`/api/dashboards/thank-you?from=${encodeURIComponent(weekStart)}&to=${encodeURIComponent(weekStart)}`),
      ]);
      thankData = { votes: thankVotes.votes, stars: thankDashboard.stars };
    } catch (error) {
      throw new Error(`生成会议邮件失败：读取 Thank You 数据失败，${errorReason(error)}`);
    }
  }
  const text = buildMeetingMinutesText(meeting, thankData);
  const html = buildMeetingMinutesHtml(meeting, thankData);
  const copyResult = await copyMeetingMinutes(html, text);
  const mailResult = openMailDraft(meetingMinutesSubject(meeting));
  if (!mailResult.ok) {
    throw new Error(`生成会议邮件失败：无法唤起邮件客户端，${mailResult.reason}。请确认 Windows 默认邮件应用已设置为 Outlook。`);
  }
  if (!copyResult.ok) {
    toast(`已尝试打开邮件草稿，但纪要复制失败。原因：${copyResult.reason}`);
    return;
  }
  const copyHint = copyResult.method === "text" || copyResult.method === "text-fallback" ? "已复制纯文本纪要" : "已复制会议纪要模板";
  const pasteHint = copyResult.method === "text" || copyResult.method === "text-fallback" ? "HTML 模板复制未生效，请在 Outlook 正文中粘贴纯文本纪要" : "请在 Outlook 正文中粘贴模板";
  toast(`已生成会议邮件，${copyHint}，${pasteHint}`);
}

function renderMeetingCalendar(meetings) {
  const month = state.meetingMonth;
  const start = monthStart(month);
  const gridStart = new Date(start);
  gridStart.setDate(start.getDate() - (start.getDay() || 7) + 1);
  const byDate = {};
  meetings.forEach((meeting) => {
    byDate[meeting.meeting_date] ||= [];
    byDate[meeting.meeting_date].push(meeting);
  });
  $("#meetingMonthTitle").textContent = `${month.getFullYear()} 年 ${month.getMonth() + 1} 月`;
  const meetingDate = $('input[name="meeting_date"]');
  if (meetingDate) meetingDate.value = state.selectedMeetingDate;
  const generateStart = $('input[name="start_date"]');
  if (generateStart && !generateStart.value) generateStart.value = mondayOf(state.selectedMeetingDate);

  const weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"].map((day) => `<div class="weekday">${day}</div>`).join("");
  const cells = [];
  for (let i = 0; i < 42; i += 1) {
    const d = new Date(gridStart);
    d.setDate(gridStart.getDate() + i);
    const date = iso(d);
    const dayMeetings = byDate[date] || [];
    const hasSelected = dayMeetings.some((meeting) => Number(meeting.id) === Number(state.selectedMeetingId));
    cells.push(`<div class="day-cell meeting-day ${d.getMonth() !== month.getMonth() ? "other" : ""} ${date === state.selectedMeetingDate ? "selected" : ""} ${hasSelected ? "active-meeting-day" : ""} ${dayMeetings.length ? "has-meeting" : ""}" data-date="${date}">
      <div class="day-no">${d.getDate()}</div>
      ${dayMeetings.map((meeting) => `<div class="meeting-line">${meeting.start_time ? `${escapeHtml(meeting.start_time)} · ` : ""}${escapeHtml(meeting.title)} · ${meeting.items.length} 议题</div>`).join("")}
    </div>`);
  }
  $("#meetingCalendar").innerHTML = weekdays + cells.join("");
}

function meetingListRange() {
  const today = iso(new Date());
  if (state.meetingListScope === "month") {
    const monthFrom = iso(monthStart(state.meetingMonth));
    const monthTo = iso(monthEnd(state.meetingMonth));
    return {
      from: monthFrom > today ? monthFrom : today,
      to: monthTo,
      label: "本月",
    };
  }
  const weekFrom = mondayOf(today);
  const weekTo = iso(addDays(`${weekFrom}T00:00:00`, 6));
  return {
    from: today > weekFrom ? today : weekFrom,
    to: weekTo,
    label: "本周",
  };
}

function upcomingMeetings(meetings = state.meetings) {
  const range = meetingListRange();
  return meetings
    .filter((meeting) => meeting.meeting_date >= range.from && meeting.meeting_date <= range.to)
    .sort((a, b) => String(a.meeting_date).localeCompare(String(b.meeting_date)) || Number(a.id) - Number(b.id));
}

function renderMeetingList(meetings) {
  const list = $("#meetingList");
  if (!list) return;
  const range = meetingListRange();
  const visibleMeetings = upcomingMeetings(meetings);
  const title = $("#meetingListTitle");
  const hint = $("#meetingListHint");
  if (title) title.textContent = `${range.label}会议`;
  if (hint) hint.textContent = `${shortDate(range.from)} 至 ${shortDate(range.to)}，只显示未过期会议。`;
  $$("[data-meeting-list-scope]").forEach((button) => {
    button.classList.toggle("active", button.dataset.meetingListScope === state.meetingListScope);
  });
  list.innerHTML = visibleMeetings.length ? visibleMeetings.map((meeting) => `
    <button type="button" class="meeting-list-item meeting-select-btn ${Number(meeting.id) === Number(state.selectedMeetingId) ? "active" : ""}" data-meeting-id="${meeting.id}">
      <span class="meeting-list-meta"><span>${escapeHtml(meetingScheduleLabel(meeting, true))}</span><em class="meeting-status-dot ${meetingStatusMeta[normalizedMeetingStatus(meeting.status)][2]}">${meetingStatusMeta[normalizedMeetingStatus(meeting.status)][0]}</em></span>
      <strong>${escapeHtml(meeting.title)}${meeting.inherited ? `<em class="meeting-source-badge">上级 · ${escapeHtml(meeting.org_unit_name || "")}</em>` : ""}</strong>
      <small>${meetingTopicTypes(meeting).length} 个主题 · ${meeting.items.length} 个议题 · ${(meeting.attendance || []).length} 条签到</small>
    </button>`).join("") : `<p>${range.label}暂无后续会议。</p>`;
}

function renderMeetingTopicScopeForm(meeting) {
  const selected = new Set((meeting.topic_type_ids || []).map((id) => Number(id)));
  if (!state.topics.length) return "<p>请先在下方维护可用的议题类型。</p>";
  return `
    <form class="meeting-topic-scope-form" data-meeting-id="${meeting.id}">
      <div class="topic-scope-grid">
        ${state.topics.map((topic) => `
          <label class="topic-scope-option">
            <input type="checkbox" name="topic_type_ids" value="${topic.id}" ${selected.has(Number(topic.id)) ? "checked" : ""}>
            <span class="topic-dot" style="background:${escapeHtml(topic.color)}"></span>
            <span>${escapeHtml(topic.name)}</span>
          </label>`).join("")}
      </div>
      <button>保存本场会议主题</button>
    </form>`;
}

function renderMeetingFlow(meeting) {
  const current = normalizedMeetingStatus(meeting.status);
  const entries = Object.entries(meetingStatusMeta);
  const currentIndex = entries.findIndex(([status]) => status === current);
  return `<div class="meeting-flow" aria-label="会议阶段">
    ${entries.map(([status, meta], index) => `
      <button type="button" class="meeting-flow-step ${index < currentIndex ? "is-past" : ""} ${status === current ? "is-current" : ""}" data-meeting-status="${status}" data-meeting-id="${meeting.id}" ${!isAdminView() || meeting.inherited ? "disabled" : ""}>
        <span>${index + 1}</span>
        <strong>${meta[0]}</strong>
        <small>${meta[1]}</small>
      </button>`).join("")}
  </div>`;
}

function meetingReadiness(meeting) {
  const items = meeting.items || [];
  const prepared = items.filter((item) => item.materials).length;
  const owned = items.filter((item) => item.owner_id).length;
  const minuted = items.filter((item) => isThankYouTopic(item) || item.minutes).length;
  return {
    prepared,
    owned,
    minuted,
    total: items.length,
    minutes: items.reduce((sum, item) => sum + Number(item.duration_minutes || 10), 0),
  };
}

function renderMeetingReadiness(meeting) {
  const readiness = meetingReadiness(meeting);
  const ratio = (value) => readiness.total ? Math.round(value / readiness.total * 100) : 0;
  return `<div class="meeting-readiness">
    <div><span>预计时长</span><strong>${readiness.minutes} 分钟</strong><small>按当前议题时间盒</small></div>
    <div><span>负责人明确</span><strong>${readiness.owned}/${readiness.total}</strong><small>${ratio(readiness.owned)}% 已分配</small></div>
    <div><span>材料就绪</span><strong>${readiness.prepared}/${readiness.total}</strong><small>${ratio(readiness.prepared)}% 已准备</small></div>
    <div><span>纪要完成</span><strong>${readiness.minuted}/${readiness.total}</strong><small>${ratio(readiness.minuted)}% 已记录</small></div>
  </div>`;
}

function renderMeetingDetail(meeting) {
  const detail = $("#meetingDetail");
  if (!detail) return;
  if (!meeting) {
    detail.innerHTML = `
      <div class="meeting-empty">
        <h2>选择一场会议</h2>
        <p>从左侧列表或上方月历选择会议后，这里会显示议题、纪要、签到和邮件入口。</p>
      </div>`;
    return;
  }
  const status = meetingStatusMeta[normalizedMeetingStatus(meeting.status)];
  const inherited = Boolean(meeting.inherited);
  const locked = meetingIsLocked(meeting) || inherited;
  detail.innerHTML = `
    <div class="meeting-detail-head">
      <div>
        <div class="meeting-title-line"><h2>${escapeHtml(meeting.title)}</h2><span class="meeting-status-badge ${status[2]}">${status[0]}</span>${inherited ? `<span class="meeting-source-badge">上级安排 · ${escapeHtml(meeting.org_unit_name || "")}</span>` : ""}</div>
        <p>${escapeHtml(meetingScheduleLabel(meeting))} · ${escapeHtml(meeting.summary || "无会议摘要")}</p>
      </div>
      <div class="meeting-meta-actions">
        <span class="pill">${escapeHtml(meeting.creator || "")}</span>
        ${isAdminView() && !locked ? `<button class="secondary meeting-copy-agenda-btn" type="button" data-meeting-id="${meeting.id}">沿用上场议题</button>` : ""}
        ${canOperate("meetings", "create") && !locked ? `<button class="secondary meeting-agenda-picker-btn" type="button" data-meeting-id="${meeting.id}">选择预设议题</button>` : ""}
        <button class="secondary meeting-attendance-btn" type="button" data-meeting-id="${meeting.id}">参会签到</button>
        <button class="button-link meeting-email-btn" type="button" data-meeting-id="${meeting.id}">生成会议邮件</button>
      </div>
    </div>

    ${renderMeetingFlow(meeting)}
    ${renderMeetingReadiness(meeting)}

    <section class="detail-section">
      <h3>本场会议主题</h3>
      <p>主题会随所选预设议题自动加入，不需要单独维护。</p>
      ${meetingTopicTypes(meeting).length ? `<div class="chip-list">${meetingTopicTypes(meeting).map((topic) => `<span class="chip"><span class="topic-dot" style="background:${escapeHtml(topic.color)}"></span>${escapeHtml(topic.name)}</span>`).join("")}</div>` : `<p class="empty-note">尚未加入主题，点击“选择预设议题”开始组会议程。</p>`}
    </section>

    <section class="detail-section">
      <div class="section-headline"><div><h3>议程与纪要</h3><p>按讨论顺序排列；管理员可直接拖动议题调整顺序。</p></div><span>${meeting.items.length} 个议题</span></div>
      ${renderTopicBoard(meeting)}
    </section>

    <div class="meeting-detail-grid meeting-detail-actions ${locked ? "is-locked" : ""}">
      <section class="detail-card">
        <h3>成员自定义议题</h3>
        ${locked ? `<p class="agenda-locked-note">${inherited ? "上级团队会议在当前团队中只读。" : "会议已结束，不能继续添加议题。"}</p>` : renderCustomTopicForm(meeting)}
      </section>
      <section class="detail-card attendance-summary-card">
        <div class="section-headline"><div><h3>参会签到</h3><p>详情收进弹窗，主页面只看签到概况。</p></div><button class="secondary meeting-attendance-btn" type="button" data-meeting-id="${meeting.id}">${isAdminView() && !inherited ? "打开签到" : "查看签到"}</button></div>
        ${renderMeetingAttendanceSummary(meeting)}
      </section>
    </div>

    <details class="detail-section meeting-secondary-section">
      <summary>查看本月参会看板</summary>
      <div class="section-headline"><h3>本月参会看板</h3><span>${state.meetings.length} 场会议</span></div>
      ${renderAttendanceDashboard(state.meetings)}
    </details>`;
  $$(".admin-only", detail).forEach((el) => el.classList.toggle("hidden", !isAdminView()));
}

async function loadMeetings() {
  const data = await api(`/api/meetings?${meetingPeriodQuery()}`);
  state.meetings = data.meetings;
  state.meetingUsers = data.attendance_users || [];
  state.coordinationUsers = data.coordination_users || state.meetingUsers;
  populateSelects();
  const visibleMeetings = upcomingMeetings(state.meetings);
  const selectedStillVisible = visibleMeetings.some((meeting) => Number(meeting.id) === Number(state.selectedMeetingId));
  if (!selectedStillVisible) {
    const sameDate = visibleMeetings.find((meeting) => meeting.meeting_date === state.selectedMeetingDate);
    state.selectedMeetingId = sameDate?.id || visibleMeetings[0]?.id || null;
  }
  const selectedMeeting = state.meetings.find((meeting) => Number(meeting.id) === Number(state.selectedMeetingId));
  if (selectedMeeting) state.selectedMeetingDate = selectedMeeting.meeting_date;
  renderMeetingCalendar(state.meetings);
  renderMeetingList(state.meetings);
  renderMeetingDetail(selectedMeeting);
  renderTopicPresetList();
  $("#topicTypeList").innerHTML = state.topics.length
    ? state.topics.map((topic) => `
      <span class="chip topic-type-chip">
        <span class="topic-dot" style="background:${escapeHtml(topic.color)}"></span>
        ${escapeHtml(topic.name)} · ${topic.options.length} 项
        <button class="chip-delete topic-type-delete-btn" type="button" data-topic-type-id="${topic.id}" data-topic-type-name="${escapeHtml(topic.name)}">×</button>
      </span>`).join("")
    : "<p>暂无议题类型</p>";
  populateSelects();
}

function setMeetingListScope(scope) {
  if (!["week", "month"].includes(scope)) return;
  state.meetingListScope = scope;
  const visibleMeetings = upcomingMeetings(state.meetings);
  const selectedVisible = visibleMeetings.some((meeting) => Number(meeting.id) === Number(state.selectedMeetingId));
  if (!selectedVisible) {
    state.selectedMeetingId = visibleMeetings[0]?.id || null;
    if (visibleMeetings[0]) state.selectedMeetingDate = visibleMeetings[0].meeting_date;
  }
  const selectedMeeting = state.meetings.find((meeting) => Number(meeting.id) === Number(state.selectedMeetingId));
  renderMeetingCalendar(state.meetings);
  renderMeetingList(state.meetings);
  renderMeetingDetail(selectedMeeting || null);
}

async function updateMeetingStatus(meetingId, status) {
  const meta = meetingStatusMeta[status];
  if (!meta) return;
  if (["completed", "archived"].includes(status) && !window.confirm(`确定将会议设为“${meta[0]}”吗？议题和纪要将进入只读状态。`)) return;
  const data = await api(`/api/meetings/${meetingId}`, { method: "PATCH", body: JSON.stringify({ status }) });
  state.meetings = data.meetings || state.meetings;
  await loadMeetings();
  toast(`会议已切换为${meta[0]}`);
}

async function reorderMeetingAgenda(meetingId, sourceId, targetId) {
  const meeting = state.meetings.find((entry) => Number(entry.id) === Number(meetingId));
  if (!meeting || Number(sourceId) === Number(targetId)) return;
  const items = [...meeting.items];
  const from = items.findIndex((item) => Number(item.id) === Number(sourceId));
  const to = items.findIndex((item) => Number(item.id) === Number(targetId));
  if (from < 0 || to < 0) return;
  const [moved] = items.splice(from, 1);
  items.splice(to, 0, moved);
  meeting.items = items;
  renderMeetingDetail(meeting);
  try {
    const data = await api(`/api/meetings/${meetingId}/items/reorder`, { method: "POST", body: JSON.stringify({ item_ids: items.map((item) => item.id) }) });
    state.meetings = data.meetings || state.meetings;
    renderMeetingDetail(state.meetings.find((entry) => Number(entry.id) === Number(meetingId)));
    toast("议题顺序已保存");
  } catch (error) {
    await loadMeetings();
    throw error;
  }
}

function renderAttendanceReadonly(meeting) {
  if (!meeting.attendance || !meeting.attendance.length) return "<p>管理员尚未签到</p>";
  const statusMap = { present: "出席", leave: "请假", absent: "缺席", late: "迟到" };
  return `<div class="item-list">${meeting.attendance.map((item) => {
    const donation = item.donation_required
      ? ` · 乐捐 ${Number(item.donation_amount || 0)} · ${item.donation_done ? "已收到" : "未收到"}`
      : "";
    return `<div class="item"><strong>${escapeHtml(item.display_name)}</strong><p>${statusMap[item.status] || item.status}${donation}</p></div>`;
  }).join("")}</div>`;
}

async function loadLinks() {
  const data = await api("/api/links");
  state.links = data.links;
  renderLinks();
}

function splitKeywords(value = "") {
  return String(value)
    .split(/[,\uff0c、\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function inferLinkKeywords(data = {}) {
  const source = [data.title, data.url, data.description, data.category].filter(Boolean).join(" ");
  const lower = source.toLowerCase();
  const machines = [];
  state.machines.forEach((machine) => {
    const name = machine.name || "";
    if (name && lower.includes(name.toLowerCase()) && !machines.includes(name)) machines.push(name);
  });
  const machineMatches = source.match(/TOPTB|机台\s*[A-Z]|老化测试台/g) || [];
  machineMatches.forEach((item) => {
    const normalized = item.replace(/\s+/g, " ");
    if (!machines.includes(normalized)) machines.push(normalized);
  });

  const rules = [
    ["会议", "会议"], ["例会", "会议"], ["纪要", "纪要"], ["模板", "模板"],
    ["看板", "看板"], ["dashboard", "看板"], ["数据", "数据"], ["交接", "交接"],
    ["报修", "报修"], ["工单", "工单"], ["sop", "SOP"], ["标准", "SOP"],
    ["复盘", "复盘"], ["质量", "质量"], ["点检", "点检"], ["白板", "白板"],
    ["miro", "白板"], ["备份", "备份"], ["审计", "审计"], ["排班", "排班"],
    ["红黑榜", "红黑榜"], ["thank", "Thank You"], ["工具", "工具"], ["文档", "文档"],
    ["流程", "流程"], ["系统", "系统"],
  ];
  const tags = [];
  rules.forEach(([needle, tag]) => {
    if (lower.includes(needle.toLowerCase()) && !tags.includes(tag)) tags.push(tag);
  });
  splitKeywords(data.category).forEach((item) => {
    if (tags.length < 4 && !tags.includes(item)) tags.push(item);
  });
  return {
    machine_scope: machines.slice(0, 4),
    process_tags: tags.slice(0, 5),
  };
}

function applyLinkKeywordSuggestion(form, force = false) {
  if (!form) return;
  const raw = Object.fromEntries(new FormData(form).entries());
  const suggestion = inferLinkKeywords(raw);
  const machineInput = form.elements.machine_scope;
  const tagInput = form.elements.process_tags;
  if (machineInput && (force || !machineInput.value.trim() || machineInput.dataset.autoSuggested === "1")) {
    machineInput.value = suggestion.machine_scope.join(", ");
    machineInput.dataset.autoSuggested = suggestion.machine_scope.length ? "1" : "";
  }
  if (tagInput && (force || !tagInput.value.trim() || tagInput.dataset.autoSuggested === "1")) {
    tagInput.value = suggestion.process_tags.join(", ");
    tagInput.dataset.autoSuggested = suggestion.process_tags.length ? "1" : "";
  }
}

function prepareLinkPayload(data) {
  const suggestion = inferLinkKeywords(data);
  if (!data.machine_scope && suggestion.machine_scope.length) data.machine_scope = suggestion.machine_scope.join(", ");
  if (!data.process_tags && suggestion.process_tags.length) data.process_tags = suggestion.process_tags.join(", ");
  return data;
}

function compareLinksForDisplay(a, b) {
  const invalidDelta = Number(a.invalid === 1) - Number(b.invalid === 1);
  if (invalidDelta) return invalidDelta;
  const pinnedDelta = Number(b.pinned === 1) - Number(a.pinned === 1);
  if (pinnedDelta) return pinnedDelta;
  const clickDelta = Number(b.click_count || 0) - Number(a.click_count || 0);
  if (clickDelta) return clickDelta;
  return String(a.title || "").localeCompare(String(b.title || ""), "zh-CN");
}

function linkTagTone(value, index = 0) {
  const text = String(value || "");
  let hash = index + 1;
  for (const char of text) hash = (hash * 31 + char.codePointAt(0)) % 997;
  return `tone-${(hash % 6) + 1}`;
}

function renderLinks() {
  const category = $("#linkCategoryFilter")?.value || "";
  const status = $("#linkStatusFilter")?.value || "";
  const keyword = ($("#linkKeywordSearch")?.value || "").trim().toLowerCase();
  const filtered = state.links.filter((link) => {
    const hitCategory = !category || link.category === category;
    const hitStatus = !status
      || (status === "valid" && Number(link.invalid) !== 1)
      || (status === "pinned" && Number(link.pinned) === 1)
      || (status === "invalid" && Number(link.invalid) === 1);
    const text = [
      link.title,
      link.url,
      link.description,
      link.category,
      link.quality_note,
      ...(link.machine_scope || []),
      ...(link.process_tags || []),
    ].filter(Boolean).join(" ").toLowerCase();
    return hitCategory && hitStatus && (!keyword || text.includes(keyword));
  }).sort(compareLinksForDisplay);
  const canEdit = canOperate("links", "edit");
  const canDelete = canOperate("links", "delete");
  const canManage = canEdit || canDelete;
  const manageHeader = canManage ? "<th>操作</th>" : "";
  $("#linkList").innerHTML = filtered.length ? `
    <table class="link-list-table ${canManage ? "has-manage" : ""}">
      <thead><tr><th>名称</th><th>适用范围</th><th>地址</th><th>点击</th>${manageHeader}</tr></thead>
      <tbody>
        ${filtered.map((link) => {
          const scope = [...(link.machine_scope || []), ...(link.process_tags || [])];
          const scopeText = scope.join(", ") || "-";
          const addressText = [link.url, link.description].filter(Boolean).join(" · ");
          return `
          <tr class="${Number(link.invalid) === 1 ? "link-invalid" : ""}">
            <td>
              <div class="link-single-line link-name-line" title="${escapeHtml(link.title)}">
                <strong>${escapeHtml(link.title)}</strong>
                <span class="tag link-tag ${linkTagTone(link.category, 0)}">${escapeHtml(link.category || "通用")}</span>
                ${Number(link.pinned) === 1 ? '<span class="pill link-pinned-pill">置顶</span>' : ""}
                ${Number(link.invalid) === 1 ? '<span class="pill warn">失效</span>' : ""}
              </div>
            </td>
            <td>
              <div class="link-scope-tags" title="${escapeHtml(scopeText)}">
                ${scope.length ? scope.map((item, index) => `<span class="tag link-tag ${linkTagTone(item, index)}">${escapeHtml(item)}</span>`).join("") : '<span class="link-empty">-</span>'}
              </div>
            </td>
            <td>
              <div class="link-single-line" title="${escapeHtml(addressText)}">
                ${Number(link.invalid) === 1
                  ? `<span class="link-url disabled">${escapeHtml(link.url)}</span>`
                  : `<a class="link-url" href="/api/links/${link.id}/open" target="_blank" rel="noreferrer">${escapeHtml(link.url)}</a>`}
                ${link.description ? `<span class="link-description"> · ${escapeHtml(link.description)}</span>` : ""}
              </div>
            </td>
            <td><span title="${escapeHtml(link.last_clicked_at || "")}">${Number(link.click_count || 0)} 次</span></td>
            ${canManage ? `
              <td>
                <div class="link-action-menu-wrap">
                  <button class="link-action-menu-toggle" type="button" data-link-menu-toggle data-link-id="${link.id}" aria-label="更多操作" title="更多操作" aria-expanded="false">⋯</button>
                  <div class="link-action-menu hidden" data-link-menu="${link.id}">
                    ${canEdit ? `<button class="link-edit-btn" type="button" data-link-id="${link.id}">编辑链接</button>` : ""}
                    ${canDelete ? `<button class="link-delete-btn danger-text" type="button" data-link-id="${link.id}">删除链接</button>` : ""}
                  </div>
                </div>
                ${isAdminView() ? `<form class="link-quality-form" data-link-id="${link.id}">
                  <select name="pinned">
                    <option value="0" ${Number(link.pinned) === 1 ? "" : "selected"}>不置顶</option>
                    <option value="1" ${Number(link.pinned) === 1 ? "selected" : ""}>置顶</option>
                  </select>
                  <select name="invalid">
                    <option value="0" ${Number(link.invalid) === 1 ? "" : "selected"}>可用</option>
                    <option value="1" ${Number(link.invalid) === 1 ? "selected" : ""}>失效</option>
                  </select>
                  <input name="machine_scope" value="${escapeHtml((link.machine_scope || []).join(", "))}" placeholder="适用机台">
                  <input name="process_tags" value="${escapeHtml((link.process_tags || []).join(", "))}" placeholder="流程标签">
                  <input name="quality_note" value="${escapeHtml(link.quality_note || "")}" placeholder="质量备注">
                  <button>保存</button>
                </form>` : ""}
              </td>` : ""}
          </tr>`;
        }).join("")}
      </tbody>
    </table>` : "<p>没有匹配的链接</p>";
}

function renderShiftLine(shift) {
  const isNight = shift.shift_type === "night";
  const isMine = Number(shift.user_id) === Number(state.user?.id);
  const typeText = isNight ? "夜" : "白";
  const fullText = `${typeText}班 · ${shift.machine_name || ""} · ${shift.display_name || ""}`;
  const adminAction = isAdminView();
  return `<div class="shift-line ${isNight ? "night" : ""} ${isMine ? "mine" : ""} ${adminAction ? "has-action" : ""}" title="${escapeHtml(fullText)}">
    <span class="shift-line-main">
      <span class="shift-type">${typeText}</span>
      <span class="shift-machine">${escapeHtml(shift.machine_name)}</span>
      <span class="shift-user">${escapeHtml(shift.display_name)}</span>
    </span>
    ${adminAction ? `<button class="shift-delete-btn" type="button" data-shift-id="${shift.id}" title="删除排班">×</button>` : ""}
  </div>`;
}

function renderMachineList() {
  const target = $("#machineList");
  if (!target) return;
  target.innerHTML = state.machines.length
    ? state.machines.map((machine) => {
      const shiftCount = state.shifts.filter((shift) => Number(shift.machine_id) === Number(machine.id)).length;
      return `<div class="machine-item">
        <div>
          <strong>${escapeHtml(machine.name)}</strong>
          <span>${machine.description ? escapeHtml(machine.description) : "暂无说明"}</span>
        </div>
        <small>${shiftCount} 条本月排班</small>
        <button class="danger machine-delete-btn" type="button" data-machine-id="${machine.id}" data-machine-name="${escapeHtml(machine.name)}">删除</button>
      </div>`;
    }).join("")
    : `<p class="empty-note">暂无机台，先新增一个机台用于排班。</p>`;
}

function shiftTypeLabel(shift) {
  return shift.shift_type === "night" ? "夜班" : "白班";
}

function renderShiftDayPopover(date, shifts) {
  if (!shifts.length) return "";
  const sorted = [...shifts].sort((a, b) => {
    const typeOrder = (a.shift_type === "night" ? 1 : 0) - (b.shift_type === "night" ? 1 : 0);
    if (typeOrder) return typeOrder;
    return String(a.machine_name || "").localeCompare(String(b.machine_name || ""), "zh-CN");
  });
  return `<div class="shift-day-popover" role="tooltip">
    <div class="shift-popover-head">
      <strong>${escapeHtml(shortDate(date))} 排班详情</strong>
      <span>${sorted.length} 条</span>
    </div>
    <div class="shift-popover-list">
      ${sorted.map((shift) => `
        <div class="shift-popover-row ${shift.shift_type === "night" ? "night" : "day"}">
          <span class="shift-popover-type">${escapeHtml(shiftTypeLabel(shift))}</span>
          <div>
            <strong>${escapeHtml(shift.machine_name || "未填写机台")}</strong>
            <span>支撑人员：${escapeHtml(shift.display_name || "未指定")}</span>
            <small>${Number(shift.hours || 0) ? `${Number(shift.hours)} 小时` : "未填写工时"}${shift.note ? ` · ${escapeHtml(shift.note)}` : ""}</small>
          </div>
          ${isAdminView() ? `<button class="shift-delete-btn shift-popover-delete" type="button" data-shift-id="${shift.id}" title="删除这条排班">删除</button>` : ""}
        </div>`).join("")}
    </div>
  </div>`;
}

function renderCalendar() {
  const month = state.shiftMonth;
  const start = monthStart(month);
  const end = monthEnd(month);
  const gridStart = new Date(start);
  gridStart.setDate(start.getDate() - (start.getDay() || 7) + 1);
  const byDate = {};
  state.shifts.forEach((shift) => {
    byDate[shift.shift_date] ||= [];
    byDate[shift.shift_date].push(shift);
  });
  const title = `${month.getFullYear()} 年 ${month.getMonth() + 1} 月`;
  $("#shiftMonthTitle").textContent = title;
  $("#shiftMonthTitle2").textContent = title;
  $("#selectedShiftDateTitle").textContent = isAdminView()
    ? `编辑排班 · ${state.selectedShiftDate}`
    : (state.user ? "我的本月排班" : "本月排班");
  const shiftStartInput = $('input[name="shift_start_date"]');
  const shiftEndInput = $('input[name="shift_end_date"]');
  if (shiftStartInput) shiftStartInput.value = state.selectedShiftDate;
  if (shiftEndInput) shiftEndInput.value = state.selectedShiftEndDate;

  const weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"].map((day) => `<div class="weekday">${day}</div>`).join("");
  const cells = [];
  for (let i = 0; i < 42; i += 1) {
    const d = new Date(gridStart);
    d.setDate(gridStart.getDate() + i);
    const date = iso(d);
    const shifts = byDate[date] || [];
    const hasMine = shifts.some((shift) => Number(shift.user_id) === Number(state.user?.id));
    const hasShifts = shifts.length > 0;
    const popoverOpen = hasShifts && state.activeShiftPopoverDate === date;
    const detailLabel = hasShifts
      ? `${date}，${shifts.length} 条排班，点击查看机台和支撑人员`
      : `${date}，暂无排班`;
    cells.push(`<div class="day-cell shift-day ${d.getMonth() !== month.getMonth() ? "other" : ""} ${date === state.selectedShiftDate ? "selected" : ""} ${hasMine ? "has-mine" : ""} ${hasShifts ? "has-shifts" : ""} ${popoverOpen ? "popover-open" : ""}" data-date="${date}" tabindex="0" aria-label="${escapeHtml(detailLabel)}">
      <div class="day-no">${d.getDate()}</div>
      ${shifts.map(renderShiftLine).join("")}
      ${renderShiftDayPopover(date, shifts)}
    </div>`);
  }
  $("#shiftCalendar").innerHTML = weekdays + cells.join("");
  renderMachineList();
}

function selectShiftDay(cell) {
  if (!cell) return;
  const date = cell.dataset.date;
  state.selectedShiftDate = date;
  state.selectedShiftEndDate = date;
  state.activeShiftPopoverDate = cell.classList.contains("has-shifts") ? date : null;
  renderCalendar();
}

function closeShiftPopover() {
  state.activeShiftPopoverDate = null;
  $$(".shift-day.popover-open").forEach((cell) => cell.classList.remove("popover-open"));
}

async function loadShifts() {
  const [list, dashboard] = await Promise.all([
    api(`/api/shifts?${shiftPeriodQuery()}`),
    api(`/api/dashboards/shifts?${shiftPeriodQuery()}`),
  ]);
  state.shifts = list.shifts;
  state.shiftUsers = list.users || [];
  $("#shiftStats").innerHTML = renderRank(dashboard.by_user, "hours", "小时");
  populateSelects();
  renderCalendar();
}

function renderThankPeriodControls() {
  const target = $("#thankPeriodControls");
  if (!target) return;
  const months = Array.from({ length: 12 }, (_, index) => index + 1);
  const currentYear = new Date().getFullYear();
  const years = Array.from(new Set([
    state.thankYear,
    ...Array.from({ length: 7 }, (_, index) => currentYear - 5 + index),
  ])).sort((a, b) => b - a);
  const monthValue = state.thankScope === "year" ? "year" : String(state.thankMonth);
  target.innerHTML = `
    <label>年份
      <select id="thankYearSelect">
        ${years.map((year) => `<option value="${year}" ${year === state.thankYear ? "selected" : ""}>${year} 年</option>`).join("")}
      </select>
    </label>
    <label>月份
      <select id="thankMonthSelect">
        <option value="year" ${monthValue === "year" ? "selected" : ""}>全年</option>
        ${months.map((month) => `<option value="${month}" ${monthValue === String(month) ? "selected" : ""}>${month} 月</option>`).join("")}
      </select>
    </label>
  `;
  const label = $("#thankPeriodLabel");
  if (label) label.textContent = `${thankPeriodRange().label} Thank You 统计`;
}

async function loadThanks() {
  renderThankPeriodControls();
  const [votes, dashboard] = await Promise.all([
    api(`/api/thank-you?${thankPeriodQuery()}`),
    api(`/api/dashboards/thank-you?${thankPeriodQuery()}`),
  ]);
  state.thankUsers = votes.users || state.thankUsers;
  populateSelects();
  $("#thankStars").innerHTML = renderThankRank(dashboard.stars || []);
  $("#thankList").innerHTML = votes.votes.length ? votes.votes.map((vote) => `
    <div class="item thank-item">
      <div class="thank-item-head">
        <h3>${escapeHtml(vote.voter_name)} → ${escapeHtml(vote.receiver_name)}${vote.cross_team ? `<span class="thank-cross-team-badge">跨团队 · ${escapeHtml(vote.voter_org_name || "")} → ${escapeHtml(vote.receiver_org_name || "")}</span>` : ""}</h3>
        ${canManageThankVote(vote) && (canOperate("thanks", "edit") || canOperate("thanks", "delete")) ? `
          <div class="thank-item-actions">
            ${canOperate("thanks", "edit") ? `<button class="secondary thank-edit-btn" type="button" data-vote-id="${vote.id}" data-evidence="${escapeHtml(vote.evidence || "")}">编辑</button>` : ""}
            ${canOperate("thanks", "delete") ? `<button class="danger thank-delete-btn" type="button" data-vote-id="${vote.id}" data-vote-title="${escapeHtml(vote.voter_name)} → ${escapeHtml(vote.receiver_name)}">删除</button>` : ""}
          </div>` : ""}
      </div>
      <p>${escapeHtml(vote.evidence)}</p>
      <p class="thank-date-line">周次 ${escapeHtml(shortDate(vote.week_start))} · 送出 ${escapeHtml(shortDateTime(vote.created_at))}</p>
    </div>`).join("") : "<p>暂无感谢记录</p>";
}

function canManageThankVote(vote) {
  if (!state.user) return false;
  if (isAdminView()) return true;
  return Number(vote.voter_id) === Number(state.user.id) && isTodayValue(vote.created_at);
}

function thankFormPayload(form) {
  const data = fullFormData(form);
  const receiverIds = new FormData(form).getAll("receiver_ids").filter(Boolean);
  if (!receiverIds.length) throw new Error("请选择至少 1 位感谢对象");
  return {
    receiver_ids: receiverIds,
    week_start: data.week_start,
    evidence: data.evidence,
  };
}

function updateThankRecipientPicker(picker) {
  if (!picker) return;
  const checked = $$('input[name="receiver_ids"]:checked', picker);
  const names = checked.map((input) => input.dataset.name || input.value);
  const label = $("[data-thank-selected-label]", picker);
  const count = $("[data-thank-selected-count]", picker);
  if (label) label.textContent = names.length ? names.join("、") : "选择感谢对象（可多选）";
  if (count) count.textContent = `${names.length} 人`;
}

function canLoadPageData(id) {
  if (id === "dashboard") return !isGuest() && canLoadModule(id);
  if (id === "meetings") return canLoadModule(id);
  if (id === "users" || id === "system") return isAdminView();
  if (id === "archive") return canLoadModule(id);
  return canLoadModule(id);
}

async function refreshPageData(id = state.currentPage) {
  const requestId = ++activePageRefreshId;
  await loadReferenceData();
  if (requestId !== activePageRefreshId) return;
  if (!canLoadPageData(id)) return;
  const loaders = {
    members: loadMembers,
    moments: loadMoments,
    dashboard: loadDashboard,
    archive: loadArchive,
    morning: loadMorning,
    processes: loadProcesses,
    meetings: loadMeetings,
    shifts: loadShifts,
    rules: loadRulesAndScores,
    thanks: loadThanks,
    links: loadLinks,
    users: loadUsers,
    system: loadSystemAdmin,
  };
  const loader = loaders[id];
  if (loader) await loader();
  renderNav();
}

async function refreshAll() {
  await loadReferenceData();
  const loaders = [];
  if (canLoadModule("rules")) loaders.push(loadRulesAndScores);
  if (canLoadModule("members")) loaders.push(loadMembers);
  if (canLoadModule("moments")) loaders.push(loadMoments);
  if (canLoadModule("morning")) loaders.push(loadMorning);
  if (!isGuest() && canLoadModule("processes")) loaders.push(loadProcesses);
  if (canLoadModule("links")) loaders.push(loadLinks);
  if (canLoadModule("shifts")) loaders.push(loadShifts);
  if (canLoadModule("thanks")) loaders.push(loadThanks);
  if (canLoadModule("archive")) loaders.push(loadArchive);
  if (!isGuest() && canLoadModule("dashboard")) loaders.push(loadDashboard);
  if (canLoadModule("meetings")) loaders.push(loadMeetings);
  if (isAdminView()) {
    loaders.push(loadUsers, loadSystemAdmin);
  }
  await Promise.all(loaders.map((loader) => loader()));
  applyAuthView();
}

function bindForm(id, handler) {
  const form = $(id);
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await handler(formData(form), form);
      form.reset();
      syncMorningChoiceGroups(form);
      setDefaultDates();
      await refreshAll();
      toast("已保存");
    } catch (error) {
      toast(error.message);
      if (error.status === 409) {
        refreshPageData(state.currentPage).catch(() => {});
      }
    }
  });
}

async function submitMemberForm(form) {
  const data = formData(form);
  const file = form.elements.avatar_file?.files?.[0];
  const avatar = await fileToDataUrl(file);
  if (avatar) data.avatar_url = avatar;
  await api("/api/members", { method: "POST", body: JSON.stringify(data) });
}

async function submitAvatarForm(form) {
  const data = formData(form);
  const file = form.elements.avatar_file?.files?.[0];
  const avatar = await fileToDataUrl(file);
  if (avatar) data.avatar_url = avatar;
  if (!data.avatar_url) throw new Error("请选择本地头像图片");
  await api(`/api/members/${form.dataset.memberId}`, { method: "PATCH", body: JSON.stringify({ avatar_url: data.avatar_url }) });
}

async function submitProfileForm(form) {
  const data = formData(form);
  const file = form.elements.avatar_file?.files?.[0];
  const avatar = await fileToDataUrl(file);
  const payload = {
    title: data.title || "",
    tags: data.tags || "",
    responsibilities: data.responsibilities || "",
    comment: data.comment || "",
    skills: data.skills || "",
    machine_scope: data.machine_scope || "",
    expertise: data.expertise || "",
  };
  if (avatar) payload.avatar_url = avatar;
  await api(`/api/members/${form.dataset.memberId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

async function submitUserEditForm(form) {
  const data = formData(form);
  const response = await api(`/api/users/${form.dataset.userId}`, { method: "PATCH", body: JSON.stringify(data) });
  state.users = response.users || state.users;
  if (Number(form.dataset.userId) === Number(state.user?.id)) {
    state.user.username = data.username || state.user.username;
    state.user.display_name = data.display_name || state.user.display_name;
    if (data.role) state.user.role = data.role;
    if (data.user_type) state.user.user_type = data.user_type;
    applyAuthView();
  }
}

function renderReactionControls(targetType, targetId, reactions = [], replyAction = "", trailingAction = "") {
  const renderCount = (item) => `${renderReactionMark(item.reaction)} <span>+${Number(item.count || 0)}</span>`;
  if (isGuest() || !canOperate("members", "create")) {
    if (!reactions.length) return "";
    return `<div class="chat-reactions readonly">
      ${reactions.map((item) => `<span class="chat-reaction-count">${renderCount(item)}</span>`).join("")}
    </div>`;
  }
  return `<div class="chat-reactions chat-reaction-wrap">
    <button type="button" class="chat-reaction-picker-toggle" data-reaction-target="${targetType}" data-reaction-id="${targetId}">表情</button>
    ${replyAction}
    ${reactions.length ? `<span class="chat-action-caption">回应</span>${reactions.map((item) => `<button type="button" class="chat-reaction-chip ${item.mine ? "active" : ""}" data-reaction-target="${targetType}" data-reaction-id="${targetId}" data-reaction="${escapeHtml(item.reaction)}">${renderCount(item)}</button>`).join("")}` : ""}
    ${trailingAction}
  </div>`;
}

function renderTeamReactions(post) {
  return renderReactionControls("post", post.id, post.reactions || []);
}

function reactionAssetKey(reaction) {
  return Array.from(String(reaction || ""))
    .map((char) => char.codePointAt(0).toString(16).toLowerCase())
    .filter((code) => code !== "fe0f")
    .join("-");
}

function renderReactionMark(reaction) {
  const text = String(reaction || "");
  const label = teamReactionLabels[text] || "历史表情";
  const asset = teamReactionEmojiAssets[reactionAssetKey(text)];
  if (!asset) {
    const looksLikeEmoji = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(text);
    if (looksLikeEmoji) {
      return `<span class="chat-reaction-text" title="${escapeHtml(label)}">${escapeHtml(text)}</span>`;
    }
    return `<span class="chat-reaction-text">${escapeHtml(text)}</span>`;
  }
  return `<img class="chat-reaction-emoji-img" src="${asset}" alt="${escapeHtml(label)}" title="${escapeHtml(label)}" loading="lazy" decoding="async">`;
}

function closeReactionPopover() {
  const popover = $("#teamReactionPopover");
  if (popover) {
    popover.classList.add("hidden");
    popover.style.left = "";
    popover.style.top = "";
  }
  activeReactionTarget = null;
}

async function sendTeamReaction(targetType, targetId, reaction) {
  if (!targetId || !reaction || !["post", "reply"].includes(targetType)) {
    throw new Error("回应发送失败：缺少对话或回应内容，请重新打开回应面板");
  }
  const resource = targetType === "reply" ? "team-replies" : "team-posts";
  const data = await api(`/api/${resource}/${targetId}/reactions`, {
    method: "POST",
    body: JSON.stringify({ reaction }),
  });
  closeReactionPopover();
  renderTeamChat(data.posts, true);
  toast("回应已更新");
}

function ensureReactionPopover() {
  let popover = $("#teamReactionPopover");
  if (popover) return popover;
  popover = document.createElement("div");
  popover.id = "teamReactionPopover";
  popover.className = "chat-reaction-picker hidden";
  popover.innerHTML = `
    <div class="chat-reaction-picker-title">选择表情</div>
    <div class="chat-reaction-picker-section-title">本地表情与快捷文字</div>
    <div class="chat-reaction-quick team-reaction-static-grid">
      ${teamReactionOptions.map((reaction) => {
        const label = teamReactionLabels[reaction] || reaction;
        const hasLocalImage = Boolean(teamReactionEmojiAssets[reactionAssetKey(reaction)]);
        const content = hasLocalImage
          ? `${renderReactionMark(reaction)}<span class="chat-reaction-option-label">${escapeHtml(label)}</span>`
          : `<span class="chat-reaction-option-label">${escapeHtml(label)}</span>`;
        return `<button type="button" class="chat-reaction-option" data-reaction="${escapeHtml(reaction)}" aria-label="${escapeHtml(label)}" title="${escapeHtml(label)}">${content}</button>`;
      }).join("")}
    </div>
    <div class="chat-reaction-picker-section-title">Emoji 表情库</div>
    <div class="team-reaction-emoji-library">
      <emoji-picker class="team-reaction-emoji-picker" locale="zh" data-source="${teamReactionEmojiDataSource}"></emoji-picker>
    </div>`;
  popover.addEventListener("click", (event) => {
    const option = event.target.closest(".chat-reaction-option");
    if (!option) return;
    event.preventDefault();
    event.stopPropagation();
    const targetType = popover.dataset.reactionTarget || activeReactionTarget?.type;
    const targetId = popover.dataset.reactionId || activeReactionTarget?.id;
    sendTeamReaction(targetType, targetId, option.dataset.reaction).catch((error) => toast(error.message));
  });
  const picker = $("emoji-picker", popover);
  if (picker) {
    picker.locale = "zh";
    picker.i18n = zhCnEmojiI18n;
    picker.dataSource = teamReactionEmojiDataSource;
    picker.addEventListener("emoji-click", (event) => {
      const reaction = event.detail?.unicode || event.detail?.emoji?.unicode || event.detail?.emoji?.emoji || "";
      if (!reaction) return toast("没有识别到表情，请重新选择");
      const targetType = popover.dataset.reactionTarget || activeReactionTarget?.type;
      const targetId = popover.dataset.reactionId || activeReactionTarget?.id;
      sendTeamReaction(targetType, targetId, reaction).catch((error) => toast(error.message));
    });
  }
  document.body.appendChild(popover);
  return popover;
}

function openReactionPopover(button) {
  const popover = ensureReactionPopover();
  const nextTarget = {
    type: button.dataset.reactionTarget || "post",
    id: button.dataset.reactionId,
  };
  const isSameOpen = activeReactionTarget?.type === nextTarget.type
    && String(activeReactionTarget?.id) === String(nextTarget.id)
    && !popover.classList.contains("hidden");
  if (isSameOpen) {
    closeReactionPopover();
    return;
  }
  activeReactionTarget = nextTarget;
  popover.dataset.reactionTarget = nextTarget.type;
  popover.dataset.reactionId = nextTarget.id;
  document.body.appendChild(popover);
  popover.classList.remove("hidden");
  const buttonRect = button.getBoundingClientRect();
  const popoverWidth = popover.offsetWidth || Math.min(360, window.innerWidth - 24);
  const popoverHeight = popover.offsetHeight || Math.min(390, window.innerHeight - 24);
  const left = Math.max(8, Math.min(buttonRect.left, window.innerWidth - popoverWidth - 8));
  const preferBottom = buttonRect.bottom + 8;
  const top = preferBottom + popoverHeight <= window.innerHeight
    ? preferBottom
    : Math.max(8, buttonRect.top - popoverHeight - 8);
  popover.style.left = `${left}px`;
  popover.style.top = `${top}px`;
}

function forumCategory(post = {}) {
  return forumCategoryMeta[post.category] || forumCategoryMeta.general;
}

function forumFilteredPosts() {
  const keyword = state.forumSearch.trim().toLowerCase();
  const items = state.teamPosts.filter((post) => {
    if (state.forumCategory !== "all" && post.category !== state.forumCategory) return false;
    if (state.forumMineOnly && Number(post.user_id) !== Number(state.user?.id)) return false;
    if (!keyword) return true;
    return [post.title, post.content, post.display_name, post.username]
      .some((value) => String(value || "").toLowerCase().includes(keyword));
  });
  return items.sort((left, right) => {
    if (Number(right.pinned || 0) !== Number(left.pinned || 0)) return Number(right.pinned || 0) - Number(left.pinned || 0);
    if (state.forumSort === "popular") return Number(right.reply_count || 0) - Number(left.reply_count || 0);
    if (state.forumSort === "views") return Number(right.view_count || 0) - Number(left.view_count || 0);
    return String(right.updated_at || right.created_at || "").localeCompare(String(left.updated_at || left.created_at || ""));
  });
}

function renderForumSidebar() {
  const hotList = $("#forumHotTopics");
  const activeList = $("#forumActiveMembers");
  if (!hotList || !activeList) return;
  const hot = [...state.teamPosts]
    .sort((left, right) => (Number(right.reply_count || 0) * 3 + Number(right.view_count || 0)) - (Number(left.reply_count || 0) * 3 + Number(left.view_count || 0)))
    .slice(0, 3);
  hotList.innerHTML = hot.length ? hot.map((post, index) => `
    <button type="button" data-forum-post-id="${post.id}">
      <span>${index + 1}</span><span><strong>${escapeHtml(post.title || post.content)}</strong><small>${Number(post.reply_count || 0)} 回复 · ${Number(post.view_count || 0)} 浏览</small></span>
    </button>`).join("") : "<p class=\"forum-empty-note\">暂无热门讨论</p>";

  const activity = new Map();
  state.teamPosts.forEach((post) => activity.set(post.display_name, (activity.get(post.display_name) || 0) + 1 + Number(post.reply_count || 0)));
  const active = [...activity.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
  $("#forumActiveCount").textContent = `${active.length} 人`;
  activeList.innerHTML = active.length ? active.map(([name]) => `<span title="${escapeHtml(name)}">${escapeHtml(String(name || "?").slice(0, 1))}</span>`).join("") : "<small>暂无活跃成员</small>";
}

function renderForumTopics() {
  const list = $("#teamChatList");
  const pagination = $("#forumPagination");
  if (!list || !pagination) return;
  const filtered = forumFilteredPosts();
  const pages = Math.max(1, Math.ceil(filtered.length / forumPageSize));
  state.forumPage = Math.min(Math.max(1, state.forumPage), pages);
  $$("[data-forum-category]").forEach((button) => {
    const active = button.dataset.forumCategory === state.forumCategory;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  const start = (state.forumPage - 1) * forumPageSize;
  const items = filtered.slice(start, start + forumPageSize);
  list.innerHTML = items.length ? items.map((post) => {
    const category = forumCategory(post);
    const lastName = post.last_reply_name || post.display_name;
    const lastTime = post.last_reply_at || post.updated_at || post.created_at;
    return `<article class="forum-topic-row ${post.pinned ? "pinned" : ""}" data-forum-post-id="${post.id}" tabindex="0">
      <div class="forum-topic-main">
        <div class="forum-topic-title-line">
          ${post.pinned ? '<span class="forum-status-badge pinned">置顶</span>' : ""}
          ${post.inherited ? `<span class="forum-status-badge inherited">上级 · ${escapeHtml(post.org_unit_name || "")}</span>` : ""}
          ${post.status === "resolved" ? '<span class="forum-status-badge resolved">已解决</span>' : `<span class="forum-status-badge ${category.tone}">${category.label}</span>`}
          <h3>${escapeHtml(post.title || post.content)}</h3>
        </div>
        <p>${escapeHtml(post.content || "")}</p>
        <div class="forum-topic-meta"><span class="forum-author-avatar">${escapeHtml(String(post.display_name || "?").slice(0, 1))}</span><span>${escapeHtml(post.display_name || "")}</span><span>·</span><time>${escapeHtml(shortDateTime(post.created_at || ""))}</time></div>
      </div>
      <strong class="forum-topic-stat"><b>${Number(post.reply_count || 0)}</b><small>条回复</small></strong>
      <strong class="forum-topic-stat"><b>${Number(post.view_count || 0)}</b><small>次浏览</small></strong>
      <div class="forum-topic-update"><strong>${escapeHtml(lastName || "")}</strong><small>${escapeHtml(shortDateTime(lastTime || ""))}</small></div>
    </article>`;
  }).join("") : `<div class="forum-empty"><strong>没有找到讨论主题</strong><p>换个分类或关键词试试，也可以发起一条新讨论。</p></div>`;
  pagination.innerHTML = filtered.length > forumPageSize ? `
    <span>共 ${filtered.length} 个主题</span>
    <div>
      <button type="button" data-forum-page="${state.forumPage - 1}" ${state.forumPage === 1 ? "disabled" : ""}>‹</button>
      ${Array.from({ length: pages }, (_, index) => index + 1).map((page) => `<button type="button" data-forum-page="${page}" class="${page === state.forumPage ? "active" : ""}">${page}</button>`).join("")}
      <button type="button" data-forum-page="${state.forumPage + 1}" ${state.forumPage === pages ? "disabled" : ""}>›</button>
    </div>` : `<span>共 ${filtered.length} 个主题</span>`;
  renderForumSidebar();
}

function renderForumReplies(post, replies = post.replies || [], depth = 0) {
  if (!replies.length) return "";
  return `<div class="forum-replies ${depth ? "nested" : ""}">
    ${replies.map((reply) => `
      <article class="forum-reply" data-reply-id="${reply.id}">
        <div class="forum-reply-avatar">${escapeHtml(String(reply.display_name || "?").slice(0, 1))}</div>
        <div class="forum-reply-content">
          <div class="forum-reply-author"><strong>${escapeHtml(reply.display_name)}</strong><time>${escapeHtml(shortDateTime(reply.created_at || ""))}</time></div>
          <p>${escapeHtml(reply.content)}</p>
          ${isGuest() || !canOperate("members", "create") ? renderReactionControls("reply", reply.id, reply.reactions || []) : `
            <div class="chat-reply-actions">
              ${renderReactionControls(
                "reply",
                reply.id,
                reply.reactions || [],
                `<button type="button" class="chat-reply-toggle" data-post-id="${post.id}" data-parent-reply-id="${reply.id}">回复</button>`,
                (canOperate("members", "delete") && (reply.mine || isAdminView())) ? `<button type="button" class="chat-reply-delete" data-reply-id="${reply.id}">删除</button>` : "",
              )}
            </div>
            <form class="chat-reply-form hidden" data-post-id="${post.id}">
              <input name="parent_reply_id" type="hidden" value="${reply.id}">
              <input name="content" placeholder="回复 ${escapeHtml(reply.display_name)}，最多 200 字" maxlength="200" required>
              <button type="submit">发送</button>
            </form>`}
          ${renderForumReplies(post, reply.replies || [], depth + 1)}
        </div>
      </article>`).join("")}
  </div>`;
}

function renderForumDetail(post) {
  const body = $("#forumDetailBody");
  if (!body || !post) return;
  const category = forumCategory(post);
  $("#forumDetailTitle").textContent = post.title || post.content;
  const categoryBadge = $("#forumDetailCategory");
  categoryBadge.className = `forum-status-badge ${post.status === "resolved" ? "resolved" : category.tone}`;
  categoryBadge.textContent = post.status === "resolved" ? "已解决" : category.label;
  const canEditPost = !post.inherited && canOperate("members", "edit") && (post.mine || isAdminView());
  const canDeletePost = !post.inherited && canOperate("members", "delete") && (post.mine || isAdminView());
  body.innerHTML = `
    <article class="forum-original-post">
      <div class="forum-original-meta"><span class="forum-author-avatar">${escapeHtml(String(post.display_name || "?").slice(0, 1))}</span><strong>${escapeHtml(post.display_name || "")}</strong><time>${escapeHtml(shortDateTime(post.created_at || ""))}</time><span>${Number(post.view_count || 0)} 次浏览</span></div>
      <div class="forum-original-content">${escapeHtml(post.content || "").replace(/\n/g, "<br>")}</div>
      <div class="forum-original-actions">
        ${renderReactionControls("post", post.id, post.reactions || [])}
        ${canEditPost ? `<button type="button" class="secondary forum-edit-post" data-post-id="${post.id}">编辑主题</button>` : ""}
        ${canEditPost ? `<button type="button" class="secondary forum-status-toggle" data-post-id="${post.id}" data-next-status="${post.status === "resolved" ? "open" : "resolved"}">${post.status === "resolved" ? "重新讨论" : "标记已解决"}</button>` : ""}
        ${isAdminView() && !post.inherited ? `<button type="button" class="secondary forum-pin-toggle" data-post-id="${post.id}" data-next-pinned="${post.pinned ? "0" : "1"}">${post.pinned ? "取消置顶" : "置顶主题"}</button>` : ""}
        ${canDeletePost ? `<button type="button" class="danger forum-delete-post" data-post-id="${post.id}" data-post-title="${escapeHtml(post.title || "该讨论")}">删除主题</button>` : ""}
      </div>
    </article>
    <section class="forum-reply-section">
      <div class="forum-reply-section-head"><h3>${Number(post.reply_count || 0)} 条回复</h3><span>按时间顺序</span></div>
      ${renderForumReplies(post)}
      ${post.reply_count ? "" : '<div class="forum-no-replies">还没有回复，来补充第一条信息。</div>'}
    </section>
    ${isGuest() || !canOperate("members", "create") ? "" : `
      <form class="chat-reply-form forum-root-reply-form" data-post-id="${post.id}">
        <textarea name="content" maxlength="200" rows="3" placeholder="写下你的回复，最多 200 字" required></textarea>
        <button type="submit">发表回复</button>
      </form>`}`;
}

function renderTeamChat(posts) {
  state.teamPosts = posts || [];
  renderForumTopics();
  if (state.selectedForumPostId) {
    const selected = state.teamPosts.find((post) => Number(post.id) === Number(state.selectedForumPostId));
    if (selected) renderForumDetail(selected);
  }
}

function openForumCreateModal(post = null) {
  const action = post ? "edit" : "create";
  if (isGuest() || !canOperate("members", action)) return toast(post ? "当前账号无权编辑讨论" : "当前账号无权发起讨论");
  const modal = $("#forumCreateModal");
  const form = $("#teamChatForm");
  form?.reset();
  state.editingForumPostId = post ? Number(post.id) : null;
  if (post) {
    form.elements.category.value = post.category || "general";
    form.elements.title.value = post.title || "";
    form.elements.content.value = post.content || "";
  }
  $("#forumCreateTitle").textContent = post ? "编辑讨论" : "发起讨论";
  $("#forumCreateDescription").textContent = post ? "修改分类、标题或正文，保存后会更新主题时间。" : "标题说清问题，正文补充背景、现象和期望结果。";
  $("#forumSubmitButton").textContent = post ? "保存修改" : "发布讨论";
  $("#forumContentCount").textContent = `${form?.elements.content?.value.length || 0} / 2000`;
  modal?.classList.remove("hidden");
  modal?.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  form?.elements.title?.focus();
}

function closeForumCreateModal() {
  const modal = $("#forumCreateModal");
  modal?.classList.add("hidden");
  modal?.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
  state.editingForumPostId = null;
}

async function openForumDetail(postId) {
  const modal = $("#forumDetailModal");
  state.selectedForumPostId = Number(postId);
  const cached = state.teamPosts.find((post) => Number(post.id) === Number(postId));
  if (cached) renderForumDetail(cached);
  modal?.classList.remove("hidden");
  modal?.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  const data = await api(`/api/team-posts/${postId}`);
  const index = state.teamPosts.findIndex((post) => Number(post.id) === Number(postId));
  if (index >= 0) state.teamPosts[index] = data.post;
  renderForumTopics();
  renderForumDetail(data.post);
}

function closeForumDetailModal() {
  const modal = $("#forumDetailModal");
  modal?.classList.add("hidden");
  modal?.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
  state.selectedForumPostId = null;
  closeReactionPopover();
}

async function updateForumPost(postId, payload) {
  const data = await api(`/api/team-posts/${postId}`, { method: "PATCH", body: JSON.stringify(payload) });
  renderTeamChat(data.posts);
  toast("讨论主题已更新");
}

function filledText(value) {
  return String(value || "").trim();
}

function memberPersona(member, skills = []) {
  const rows = [
    ["技能", skills.map(escapeHtml).join(" / ")],
    ["擅长问题", escapeHtml(filledText(member.expertise))],
  ].filter(([, value]) => value);
  if (!rows.length) return "";
  return `<div class="member-persona">
    ${rows.map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join("")}
  </div>`;
}

function renderAvatar(member) {
  return member.avatar_url
    ? `<img class="avatar" src="${escapeHtml(member.avatar_url)}" alt="${escapeHtml(member.name)}">`
    : `<div class="avatar">${escapeHtml((member.name || "?").slice(0, 1))}</div>`;
}

function renderAvatarPreview(member) {
  return member.avatar_url ? `<img src="${escapeHtml(member.avatar_url)}" alt="${escapeHtml(member.name)}">` : escapeHtml((member.name || "?").slice(0, 1));
}

function setMemberAvatarPreview(src = "", fallback = "?") {
  const preview = $("#memberEditAvatarPreview");
  if (!preview) return;
  preview.innerHTML = src ? `<img src="${escapeHtml(src)}" alt="">` : escapeHtml((fallback || "?").slice(0, 1));
  preview.classList.toggle("has-image", Boolean(src));
}

function closePasswordModal() {
  const modal = $("#passwordModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

function openPasswordModal() {
  if (isGuest()) return;
  const modal = $("#passwordModal");
  const form = $("#passwordForm");
  if (!modal || !form) return;
  form.reset();
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  form.elements.old_password?.focus();
  loadSessions().catch((error) => toast(error.message));
}

function renderSessions() {
  const target = $("#sessionList");
  if (!target) return;
  target.innerHTML = state.sessions.length ? state.sessions.map((session) => `
    <article class="session-row ${session.current ? "current" : ""}">
      <div class="session-device-mark" aria-hidden="true">${session.device?.includes("手机") ? "▯" : "▱"}</div>
      <div class="session-row-main">
        <strong>${escapeHtml(session.device || "浏览器会话")}${session.current ? " · 当前设备" : ""}</strong>
        <span>${escapeHtml(session.ip_address || "未知地址")} · 最近活动 ${escapeHtml(shortDateTime(session.last_seen_at))}</span>
        <small>登录于 ${escapeHtml(shortDateTime(session.created_at))}，到期 ${escapeHtml(shortDateTime(session.expires_at))}</small>
      </div>
      <button class="${session.current ? "secondary" : "danger"} session-revoke-btn" type="button" data-session-id="${session.id}">${session.current ? "退出当前" : "撤销"}</button>
    </article>`).join("") : '<p class="empty-note">没有有效登录会话</p>';
}

async function loadSessions() {
  if (isGuest()) return;
  const data = await api("/api/sessions");
  state.sessions = data.sessions || [];
  renderSessions();
}

function closeMemberEditModal() {
  const modal = $("#memberEditModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

function closeLinkEditModal() {
  const modal = $("#linkEditModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

function closeLinkActionMenus(exceptId = null) {
  $$("[data-link-menu]").forEach((menu) => {
    const keepOpen = exceptId !== null && String(menu.dataset.linkMenu) === String(exceptId);
    menu.classList.toggle("hidden", !keepOpen);
  });
  $$("[data-link-menu-toggle]").forEach((button) => {
    const expanded = exceptId !== null && String(button.dataset.linkId) === String(exceptId);
    button.setAttribute("aria-expanded", expanded ? "true" : "false");
  });
}

function toggleLinkActionMenu(button) {
  const linkId = button.dataset.linkId;
  const menu = $(`[data-link-menu="${linkId}"]`);
  const shouldOpen = menu?.classList.contains("hidden");
  closeLinkActionMenus(shouldOpen ? linkId : null);
}

function closeLinkDeleteModal() {
  const modal = $("#linkDeleteModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  pendingLinkDeleteId = null;
  document.body.classList.remove("modal-open");
}

function openLinkDeleteModal(linkId) {
  if (!canOperate("links", "delete")) return;
  const link = state.links.find((item) => Number(item.id) === Number(linkId));
  const modal = $("#linkDeleteModal");
  if (!link || !modal) return;
  pendingLinkDeleteId = link.id;
  $("#linkDeleteName").textContent = link.title || "常用链接";
  $("#linkDeleteUrl").textContent = link.url || "";
  closeLinkActionMenus();
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  $("[data-link-delete-confirm]", modal)?.focus();
}

function openLinkEditModal(linkId) {
  if (!canOperate("links", "edit")) return;
  const link = state.links.find((item) => Number(item.id) === Number(linkId));
  const modal = $("#linkEditModal");
  const form = $("#linkEditForm");
  if (!link || !modal || !form) return;
  closeLinkActionMenus();
  populateSelects();
  form.dataset.linkId = link.id;
  form.elements.title.value = link.title || "";
  form.elements.url.value = link.url || "";
  form.elements.category.value = link.category || "";
  form.elements.description.value = link.description || "";
  form.elements.machine_scope.value = (link.machine_scope || []).join(", ");
  form.elements.process_tags.value = (link.process_tags || []).join(", ");
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  form.elements.title.focus();
}

async function submitLinkEditForm(form) {
  if (!canOperate("links", "edit")) throw new Error("当前账号无权编辑常用链接");
  const payload = prepareLinkPayload(fullFormData(form));
  const data = await api(`/api/links/${form.dataset.linkId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  state.links = data.links || state.links;
  renderLinks();
  closeLinkEditModal();
}

async function deleteLink(linkId) {
  if (!canOperate("links", "delete")) throw new Error("当前账号无权删除常用链接");
  const data = await api(`/api/links/${linkId}`, { method: "DELETE" });
  state.links = data.links || state.links.filter((item) => Number(item.id) !== Number(linkId));
  renderLinks();
  closeLinkDeleteModal();
  toast(data.message || "链接已删除");
}

function openMemberEditModal(memberId) {
  const member = state.members.find((item) => Number(item.id) === Number(memberId));
  const modal = $("#memberEditModal");
  const form = $("#memberEditForm");
  if (!member || !modal || !form) return;
  const skills = member.skills || [];
  const tags = member.tags || [];
  form.dataset.memberId = member.id;
  form.dataset.userId = member.user_id || "";
  form.reset();
  form.elements.title.value = member.title || "";
  form.elements.tags.value = tags.join(", ");
  form.elements.responsibilities.value = member.responsibilities || "";
  form.elements.comment.value = member.comment || "";
  form.elements.skills.value = skills.join(", ");
  form.elements.expertise.value = member.expertise || "";
  $("#memberEditName").textContent = member.name || "成员";
  $("#memberEditAccount").textContent = member.account ? `账号 ${member.account}` : "未绑定账号";
  $("#memberEditAvatarPreview").innerHTML = renderAvatarPreview(member);
  $("#memberEditAvatarPreview").classList.toggle("has-image", Boolean(member.avatar_url));
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  form.elements.title.focus();
}

function renderMemberCard(member, memberIndex = 0, memberCount = 1) {
  const canEdit = canOperate("members", "edit") && (isAdminView() || member.user_id === state.user?.id);
  const skills = member.skills || [];
  const tags = member.tags || [];
  const responsibilities = filledText(member.responsibilities);
  const comment = filledText(member.comment);
  const account = filledText(member.account);
  return `
    <article class="member-card profile-only" data-member-id="${member.id}">
      <section class="member-profile">
        ${isAdminView() ? `
          <div class="member-order-actions" aria-label="调整成员顺序">
            <span class="member-drag-handle" draggable="true" data-member-drag-id="${member.id}" title="拖动调整顺序" aria-label="拖动调整成员顺序">⋮⋮</span>
            <button class="member-order-btn" type="button" data-member-id="${member.id}" data-order-direction="up" title="向前移动" ${memberIndex === 0 ? "disabled" : ""}>↑</button>
            <button class="member-order-btn" type="button" data-member-id="${member.id}" data-order-direction="down" title="向后移动" ${memberIndex === memberCount - 1 ? "disabled" : ""}>↓</button>
          </div>` : ""}
        <div class="member-head">
          ${renderAvatar(member)}
          <div>
            <h3>${escapeHtml(member.name)}${account ? `<span class="member-account">账号 ${escapeHtml(account)}</span>` : ""}</h3>
            ${member.title ? `<p class="member-title">${escapeHtml(member.title)}</p>` : ""}
          </div>
        </div>
        ${tags.length ? `<div class="tags">${tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div>` : ""}
        <div class="member-brief">
          <p><strong>职责：</strong>${responsibilities ? escapeHtml(responsibilities) : "待补充"}</p>
          ${comment ? `<p>${escapeHtml(comment)}</p>` : ""}
        </div>
        ${memberPersona(member, skills)}
        ${canEdit ? `
          <button class="secondary member-edit-btn" type="button" data-member-id="${member.id}">编辑资料</button>` : ""}
      </section>
    </article>`;
}

function renderMemberCards() {
  return state.members.map((member, index) => renderMemberCard(member, index, state.members.length)).join("");
}

async function saveMemberOrder(nextMembers, successMessage = "成员顺序已保存") {
  const previousMembers = [...state.members];
  state.members = nextMembers;
  $("#memberList").innerHTML = renderMemberCards();
  try {
    const data = await api("/api/members/order", {
      method: "PATCH",
      body: JSON.stringify({ member_ids: state.members.map((item) => item.id) }),
    });
    state.members = data.members || state.members;
    $("#memberList").innerHTML = renderMemberCards();
    toast(successMessage);
  } catch (error) {
    state.members = previousMembers;
    $("#memberList").innerHTML = renderMemberCards();
    throw error;
  }
}

async function moveMemberCard(memberId, direction) {
  const member = state.members.find((item) => Number(item.id) === Number(memberId));
  if (!member || !isAdminView()) return;
  const index = state.members.findIndex((item) => Number(item.id) === Number(memberId));
  const swapIndex = direction === "up" ? index - 1 : index + 1;
  if (index < 0 || swapIndex < 0 || swapIndex >= state.members.length) return;
  const nextMembers = [...state.members];
  [nextMembers[index], nextMembers[swapIndex]] = [nextMembers[swapIndex], nextMembers[index]];
  await saveMemberOrder(nextMembers);
}

async function reorderMemberCards(draggedMemberId, targetMemberId, placeAfter) {
  if (!isAdminView()) return;
  const draggedId = Number(draggedMemberId);
  const targetId = Number(targetMemberId);
  if (!draggedId || !targetId || draggedId === targetId) return;
  const nextMembers = [...state.members];
  const draggedIndex = nextMembers.findIndex((member) => Number(member.id) === draggedId);
  if (draggedIndex < 0) return;
  const [dragged] = nextMembers.splice(draggedIndex, 1);
  const targetIndex = nextMembers.findIndex((member) => Number(member.id) === targetId);
  if (targetIndex < 0) return;
  nextMembers.splice(targetIndex + (placeAfter ? 1 : 0), 0, dragged);
  if (nextMembers.every((member, index) => Number(member.id) === Number(state.members[index]?.id))) return;
  await saveMemberOrder(nextMembers, "拖动排序已保存");
}

function momentMeta(moment) {
  return momentCategoryMeta[moment.category] || momentCategoryMeta.milestone;
}

function momentImagesMarkup(moment) {
  const images = moment.images || [];
  if (!images.length) {
    return `<div class="moment-image-empty" aria-hidden="true"><span>◈</span><strong>${escapeHtml(momentMeta(moment).label)}</strong></div>`;
  }
  const visible = images.slice(0, 4);
  return `<div class="moment-image-stack count-${visible.length}">
    ${visible.map((image, index) => `<button class="moment-gallery-trigger" type="button" data-moment-gallery-id="${moment.id}" data-moment-gallery-index="${index}" aria-label="查看${escapeHtml(moment.title)}第 ${index + 1} 张图片"><img src="${escapeHtml(image.url)}" alt="${escapeHtml(moment.title)} 图片 ${index + 1}" loading="lazy">${index === 3 && images.length > 4 ? `<span class="moment-image-more">查看全部 ${images.length} 张</span>` : ""}</button>`).join("")}
  </div>`;
}

function momentActionsMarkup(moment) {
  if (moment.inherited || isGuest()) return "";
  const edit = canOperate("moments", "edit") ? `<button class="secondary moment-edit-button" type="button" data-moment-id="${moment.id}">编辑</button>` : "";
  const remove = canOperate("moments", "delete") ? `<button class="danger moment-delete-button" type="button" data-moment-id="${moment.id}">删除</button>` : "";
  return edit || remove ? `<div class="moment-actions">${edit}${remove}</div>` : "";
}

function momentCardMarkup(moment, timeline = false, featured = false) {
  const meta = momentMeta(moment);
  return `<article class="moment-card ${timeline ? "timeline-card" : ""} ${featured ? "moment-featured" : ""}" data-tone="${meta.tone}">
    ${momentImagesMarkup(moment)}
    <div class="moment-card-body">
      <div class="moment-card-kicker"><span class="moment-category">${escapeHtml(meta.label)}</span><time>${escapeHtml(shortDate(moment.event_date))}</time></div>
      <h3>${escapeHtml(moment.title)}</h3>
      <p class="moment-story">${escapeHtml(moment.story)}</p>
      ${String(moment.story || "").length > 90 ? `<button class="moment-story-toggle" type="button" aria-expanded="false">阅读全文</button>` : ""}
      <div class="moment-card-footer">
        <span>${escapeHtml(moment.org_unit_name || "当前团队")} · ${escapeHtml(moment.created_by_name || "")}</span>
        ${moment.inherited ? `<span class="moment-inherited">来自上级团队</span>` : ""}
      </div>
      ${momentActionsMarkup(moment)}
    </div>
  </article>`;
}

function filteredMoments() {
  const keyword = state.momentKeyword.trim().toLowerCase();
  return state.moments.filter((moment) => {
    if (state.momentYear && String(moment.event_date || "").slice(0, 4) !== state.momentYear) return false;
    if (!keyword) return true;
    return [moment.title, moment.story, moment.org_unit_name, moment.created_by_name, momentMeta(moment).label]
      .some((value) => String(value || "").toLowerCase().includes(keyword));
  });
}

function renderMomentYearFilter() {
  const select = $("#momentYearFilter");
  if (!select) return;
  const years = [...new Set(state.moments.map((item) => String(item.event_date || "").slice(0, 4)).filter(Boolean))].sort().reverse();
  select.innerHTML = `<option value="">全部年份</option>${years.map((year) => `<option value="${year}" ${state.momentYear === year ? "selected" : ""}>${year} 年</option>`).join("")}`;
}

function renderMomentSummary() {
  const summary = $("#momentSummary");
  if (!summary) return;
  const currentYear = String(new Date().getFullYear());
  const imageCount = state.moments.reduce((total, moment) => total + (moment.images || []).length, 0);
  const currentYearCount = state.moments.filter((moment) => String(moment.event_date || "").startsWith(currentYear)).length;
  const teams = new Set(state.moments.map((moment) => moment.org_unit_name).filter(Boolean)).size;
  const metrics = [
    [state.moments.length, "关键时刻"],
    [currentYearCount, `${currentYear} 年新增`],
    [imageCount, "珍贵影像"],
    [teams || (state.moments.length ? 1 : 0), "参与团队"],
  ];
  summary.innerHTML = metrics.map(([value, label]) => `<div class="moment-summary-item"><strong>${value}</strong><span>${escapeHtml(label)}</span></div>`).join("");
}

function renderMoments() {
  const list = $("#momentList");
  if (!list) return;
  const moments = filteredMoments();
  renderMomentSummary();
  $("#momentResultCount").textContent = `共 ${moments.length} 个时刻`;
  $$('[data-moment-view]').forEach((button) => {
    const active = button.dataset.momentView === state.momentView;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  list.className = state.momentView === "timeline" ? "moment-timeline" : "moment-card-grid";
  if (!moments.length) {
    list.innerHTML = `<div class="moment-empty"><span>◈</span><h3>还没有匹配的团队时刻</h3><p>${canOperate("moments", "create") ? "记录一个关键事件，让团队成果被持续看见。" : "可以调整年份或关键词后再查看。"}</p></div>`;
    return;
  }
  if (state.momentView === "timeline") {
    list.innerHTML = moments.map((moment) => `<div class="moment-timeline-row"><div class="moment-timeline-date"><strong>${escapeHtml(compactDate(moment.event_date))}</strong><span>${escapeHtml(momentMeta(moment).label)}</span></div><span class="moment-timeline-dot" data-tone="${escapeHtml(momentMeta(moment).tone)}"></span>${momentCardMarkup(moment, true)}</div>`).join("");
    return;
  }
  list.innerHTML = moments.map((moment, index) => momentCardMarkup(moment, false, index === 0)).join("");
}

function activeMomentGallery() {
  return state.moments.find((moment) => Number(moment.id) === Number(state.activeMomentGalleryId));
}

function renderMomentGallery() {
  const modal = $("#momentGalleryModal");
  const moment = activeMomentGallery();
  const images = moment?.images || [];
  if (!modal || !moment || !images.length) return;
  const imageIndex = Math.min(Math.max(Number(state.activeMomentImageIndex) || 0, 0), images.length - 1);
  state.activeMomentImageIndex = imageIndex;
  const image = images[imageIndex];
  $("#momentGalleryTitle").textContent = moment.title || "团队时刻";
  $("#momentGalleryCategory").textContent = momentMeta(moment).label;
  $("#momentGalleryMeta").textContent = `${shortDate(moment.event_date)} · ${moment.org_unit_name || "当前团队"}`;
  $("#momentGalleryImage").src = image.url;
  $("#momentGalleryImage").alt = `${moment.title} 图片 ${imageIndex + 1}`;
  $("#momentGalleryCounter").textContent = `${imageIndex + 1} / ${images.length}`;
  $("#momentGalleryThumbs").innerHTML = images.map((item, index) => `<button type="button" data-gallery-index="${index}" class="${index === imageIndex ? "active" : ""}" aria-label="查看第 ${index + 1} 张图片" aria-pressed="${index === imageIndex ? "true" : "false"}"><img src="${escapeHtml(item.url)}" alt="" loading="lazy"></button>`).join("");
  $$('[data-gallery-step]', modal).forEach((button) => {
    button.classList.toggle("hidden", images.length < 2);
  });
}

function openMomentGallery(momentId, imageIndex = 0) {
  const modal = $("#momentGalleryModal");
  const moment = state.moments.find((item) => Number(item.id) === Number(momentId));
  if (!modal || !(moment?.images || []).length) return;
  state.activeMomentGalleryId = moment.id;
  state.activeMomentImageIndex = Number(imageIndex) || 0;
  renderMomentGallery();
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  modal.querySelector("[data-moment-gallery-close]")?.focus();
}

function closeMomentGallery() {
  const modal = $("#momentGalleryModal");
  if (!modal || modal.classList.contains("hidden")) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
  state.activeMomentGalleryId = null;
  state.activeMomentImageIndex = 0;
}

function moveMomentGallery(step) {
  const images = activeMomentGallery()?.images || [];
  if (images.length < 2) return;
  state.activeMomentImageIndex = (state.activeMomentImageIndex + Number(step) + images.length) % images.length;
  renderMomentGallery();
}

async function loadMoments() {
  const data = await api("/api/team-moments");
  state.moments = data.moments || [];
  renderMomentYearFilter();
  renderMoments();
}

function renderMomentImagePreview(moment = null, files = []) {
  const preview = $("#momentImagePreview");
  if (!preview) return;
  const selectedRemovals = new Set($$('input[name="remove_image_ids"]:checked', preview).map((input) => String(input.value)));
  const existing = (moment?.images || []).map((image) => `
    <label class="moment-preview-item existing">
      <img src="${escapeHtml(image.url)}" alt="${escapeHtml(image.filename || "已上传图片")}">
      <span><input type="checkbox" name="remove_image_ids" value="${image.id}" ${selectedRemovals.has(String(image.id)) ? "checked" : ""}> 移除</span>
    </label>`).join("");
  const incoming = [...files].map((file) => `
    <div class="moment-preview-item incoming">
      <img src="${escapeHtml(URL.createObjectURL(file))}" alt="${escapeHtml(file.name)}">
      <span>${escapeHtml(file.name)}</span>
    </div>`).join("");
  preview.innerHTML = existing || incoming ? `${existing}${incoming}` : `<p class="empty-note">可上传现场照片、成果截图或团队合影。</p>`;
}

function openMomentModal(momentId = null) {
  if (momentId && !canOperate("moments", "edit")) return;
  if (!momentId && !canOperate("moments", "create")) return;
  const modal = $("#momentEditModal");
  const form = $("#momentEditForm");
  const moment = state.moments.find((item) => Number(item.id) === Number(momentId));
  if (!modal || !form || (momentId && !moment)) return;
  state.editingMomentId = moment ? moment.id : null;
  form.reset();
  form.elements.title.value = moment?.title || "";
  form.elements.event_date.value = moment?.event_date || iso(new Date());
  form.elements.category.value = moment?.category || "milestone";
  form.elements.story.value = moment?.story || "";
  $("#momentEditTitle").textContent = moment ? "编辑团队时刻" : "记录团队时刻";
  $("#momentSubmitButton").textContent = moment ? "保存修改" : "发布团队时刻";
  renderMomentImagePreview(moment);
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  form.elements.title.focus();
}

function closeMomentModal() {
  const modal = $("#momentEditModal");
  modal?.classList.add("hidden");
  modal?.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
  state.editingMomentId = null;
}

async function submitMomentForm(form) {
  const button = $("#momentSubmitButton");
  const files = [...(form.elements.images.files || [])];
  const existingCount = state.editingMomentId
    ? (state.moments.find((item) => Number(item.id) === Number(state.editingMomentId))?.images || []).length
    : 0;
  const removeImageIds = new FormData(form).getAll("remove_image_ids").map(Number);
  if (existingCount - removeImageIds.length + files.length > 6) throw new Error("每条团队时刻最多保留 6 张图片");
  button.disabled = true;
  button.textContent = "正在处理图片…";
  try {
    const imageData = await momentFilesToData(files);
    const payload = {
      title: form.elements.title.value.trim(),
      event_date: form.elements.event_date.value,
      category: form.elements.category.value,
      story: form.elements.story.value.trim(),
    };
    const data = state.editingMomentId
      ? await api(`/api/team-moments/${state.editingMomentId}`, { method: "PATCH", body: JSON.stringify({ ...payload, new_images: imageData, remove_image_ids: removeImageIds }) })
      : await api("/api/team-moments", { method: "POST", body: JSON.stringify({ ...payload, images: imageData }) });
    state.moments = data.moments || state.moments;
    closeMomentModal();
    renderMomentYearFilter();
    renderMoments();
    toast(data.message || "团队时刻已保存");
  } finally {
    button.disabled = false;
    button.textContent = state.editingMomentId ? "保存修改" : "发布团队时刻";
  }
}

async function loadMembers() {
  const [membersData, postsData] = await Promise.all([
    api("/api/members"),
    api("/api/team-posts"),
  ]);
  state.members = membersData.members;
  renderTeamChat(postsData.posts);
  $("#memberList").innerHTML = renderMemberCards();
}

function updateOptionSelect(typeSelect) {
  const form = typeSelect.closest("form");
  const optionSelect = form?.querySelector("[data-meeting-option-select]");
  if (!optionSelect) return;
  const topic = state.topics.find((item) => Number(item.id) === Number(typeSelect.value));
  optionSelect.innerHTML = `<option value="">自定义议题</option>${(topic?.options || []).map((option) => `<option value="${option.id}">${escapeHtml(option.title)}</option>`).join("")}`;
}

function updateTopicOptionDefaults(optionSelect) {
  const form = optionSelect.closest("form");
  const optionId = Number(optionSelect.value);
  const option = state.topics.flatMap((topic) => topic.options || []).find((item) => Number(item.id) === optionId);
  if (!form || !option) return;
  if (form.elements.title && !form.elements.title.value.trim()) {
    form.elements.title.value = option.title || "";
  }
  if (form.elements.detail && !form.elements.detail.value.trim()) {
    form.elements.detail.value = option.default_detail || "";
  }
  if (form.elements.owner_id && option.owner_id && !form.elements.owner_id.value) {
    form.elements.owner_id.value = String(option.owner_id);
  }
}

function isThankYouTopic(item = {}) {
  const text = [item.type_name, item.section, item.title, item.option_title]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return text.includes("thank you") || text.includes("thankyou") || text.includes("感谢");
}

function moveMonth(delta) {
  state.shiftMonth = new Date(state.shiftMonth.getFullYear(), state.shiftMonth.getMonth() + delta, 1);
  loadShifts().catch((error) => toast(error.message));
}

function moveMeetingMonth(delta) {
  state.meetingMonth = new Date(state.meetingMonth.getFullYear(), state.meetingMonth.getMonth() + delta, 1);
  state.meetingListScope = "month";
  state.selectedMeetingDate = iso(new Date(state.meetingMonth.getFullYear(), state.meetingMonth.getMonth(), 1));
  loadMeetings().catch((error) => toast(error.message));
}

function bindEvents() {
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && state.user) syncAuthState().catch(() => {});
  });
  window.addEventListener("focus", () => {
    if (state.user) syncAuthState().catch(() => {});
  });
  window.addEventListener("pageshow", (event) => {
    if (state.user && event.persisted) syncAuthState(true).catch(() => {});
  });
  window.addEventListener("popstate", () => {
    switchPage(pageFromLocation() || state.currentPage, false);
    refreshAll().catch((error) => toast(error.message));
  });
  $("#loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const data = await api("/api/login", { method: "POST", body: JSON.stringify(formData(event.currentTarget)) });
      state.user = data.user;
      state.permissions = data.permissions;
      applyOrganizationData(data.organization || state.organization);
      state.permissionPreview = null;
      state.showLogin = false;
      safeSessionRemove("teamLoopSsoAttempted");
      safeSessionRemove("teamLoopSsoSkip");
      applyAuthView();
      switchPage(pageFromLocation() || state.currentPage);
      await refreshAll();
    } catch (error) {
      toast(error.message);
    }
  });

  $("#ssoLoginBtn")?.addEventListener("click", (event) => {
    safeSessionRemove("teamLoopSsoSkip");
    safeSessionSet("teamLoopSsoAttempted", "1");
    event.currentTarget.disabled = true;
    event.currentTarget.textContent = "正在跳转...";
    window.location.assign(ssoLoginUrl());
  });

  $("#logoutBtn").addEventListener("click", async () => {
    safeSessionSet("teamLoopSsoSkip", "1");
    try {
      await api("/api/logout", { method: "POST", body: "{}" });
    } finally {
      await transitionToLoggedOut(true, true);
    }
    toast("已退出登录");
  });

  $("#loginEntryBtn")?.addEventListener("click", () => {
    safeSessionSet("teamLoopSsoSkip", "1");
    state.showLogin = true;
    applyAuthView();
  });

  $("#passwordBtn")?.addEventListener("click", openPasswordModal);

  $("#guestBrowseBtn")?.addEventListener("click", async () => {
    safeSessionSet("teamLoopSsoSkip", "1");
    state.showLogin = false;
    applyAuthView();
    switchPage(firstAccessiblePage());
    await refreshAll();
  });
  $("#orgTreeToggle")?.addEventListener("click", () => {
    state.organizationTreeOpen = !state.organizationTreeOpen;
    renderOrganizationSwitcher();
  });
  $("#orgTreePanel")?.addEventListener("click", async (event) => {
    event.stopPropagation();
    const branch = event.target.closest("[data-org-tree-expand]");
    if (branch) {
      const unitId = Number(branch.dataset.orgTreeExpand);
      if (state.expandedOrganizationIds.has(unitId)) state.expandedOrganizationIds.delete(unitId);
      else state.expandedOrganizationIds.add(unitId);
      renderOrganizationSwitcher();
      return;
    }
    const unitButton = event.target.closest("[data-org-path]");
    if (!unitButton) return;
    try {
      await selectOrganizationPath(unitButton.dataset.orgPath);
    } catch (error) {
      toast(error.message);
    }
  });
  $("#orgTreeCollapseAll")?.addEventListener("click", () => {
    state.expandedOrganizationIds = new Set();
    renderOrganizationSwitcher();
  });
  $("#orgTreeExpandAll")?.addEventListener("click", () => {
    const units = state.organization?.accessible || [];
    const parentIds = new Set(units.map((unit) => Number(unit.parent_id)).filter(Boolean));
    state.expandedOrganizationIds = new Set(units.filter((unit) => parentIds.has(Number(unit.id))).map((unit) => Number(unit.id)));
    renderOrganizationSwitcher();
  });
  document.addEventListener("click", (event) => {
    if (!state.organizationTreeOpen || event.target.closest("#orgSwitcher")) return;
    state.organizationTreeOpen = false;
    renderOrganizationSwitcher();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !state.organizationTreeOpen) return;
    state.organizationTreeOpen = false;
    renderOrganizationSwitcher();
    $("#orgTreeToggle")?.focus();
  });
  $("#orgUnitForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = fullFormData(form);
    const id = data.id;
    delete data.id;
    data.sso_groups = String(data.sso_groups || "").split(/[,;\n]/).map((item) => item.trim()).filter(Boolean);
    if (!data.parent_id) data.parent_id = null;
    try {
      await api(id ? `/api/org-units/${id}` : "/api/org-units", { method: id ? "PATCH" : "POST", body: JSON.stringify(data) });
      closeOrgUnitModal();
      await loadUsers();
      toast(id ? "团队层级已更新" : "团队层级已创建");
    } catch (error) {
      toast(error.message);
    }
  });

  $("#nav").addEventListener("click", (event) => {
    const button = event.target.closest("[data-page]");
    if (button) {
      switchPage(button.dataset.page);
      refreshPageData(state.currentPage).catch((error) => toast(error.message));
    }
  });
  $("#sidebarAccountToggle")?.addEventListener("click", (event) => {
    const expanded = event.currentTarget.getAttribute("aria-expanded") !== "true";
    setSidebarAccountExpanded(expanded);
  });

  $("#refreshBtn").addEventListener("click", refreshAll);
  $("#momentCreateButton")?.addEventListener("click", () => openMomentModal());
  $("#momentYearFilter")?.addEventListener("change", (event) => {
    state.momentYear = event.target.value || "";
    renderMoments();
  });
  $("#momentKeywordFilter")?.addEventListener("input", (event) => {
    state.momentKeyword = event.target.value || "";
    renderMoments();
  });
  $("#momentEditForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    submitMomentForm(event.currentTarget).catch((error) => toast(error.message));
  });
  $("#momentEditForm")?.elements.images?.addEventListener("change", (event) => {
    const moment = state.moments.find((item) => Number(item.id) === Number(state.editingMomentId));
    renderMomentImagePreview(moment, event.target.files || []);
  });
  document.addEventListener("click", (event) => {
    const galleryTrigger = event.target.closest("[data-moment-gallery-id]");
    if (galleryTrigger) {
      openMomentGallery(galleryTrigger.dataset.momentGalleryId, galleryTrigger.dataset.momentGalleryIndex);
      return;
    }
    const galleryStep = event.target.closest("[data-gallery-step]");
    if (galleryStep) {
      moveMomentGallery(galleryStep.dataset.galleryStep);
      return;
    }
    const galleryThumb = event.target.closest("[data-gallery-index]");
    if (galleryThumb) {
      state.activeMomentImageIndex = Number(galleryThumb.dataset.galleryIndex) || 0;
      renderMomentGallery();
      return;
    }
    if (event.target.closest("[data-moment-gallery-close]") || event.target === $("#momentGalleryModal")) {
      closeMomentGallery();
      return;
    }
    const viewButton = event.target.closest("[data-moment-view]");
    if (viewButton) {
      state.momentView = viewButton.dataset.momentView === "timeline" ? "timeline" : "cards";
      safeStorageSet("teamLoopMomentView", state.momentView);
      renderMoments();
      return;
    }
    const editButton = event.target.closest(".moment-edit-button");
    if (editButton) {
      openMomentModal(editButton.dataset.momentId);
      return;
    }
    const storyButton = event.target.closest(".moment-story-toggle");
    if (storyButton) {
      const card = storyButton.closest(".moment-card");
      const expanded = !card.classList.contains("story-expanded");
      card.classList.toggle("story-expanded", expanded);
      storyButton.textContent = expanded ? "收起" : "阅读全文";
      storyButton.setAttribute("aria-expanded", expanded ? "true" : "false");
      return;
    }
    const deleteButton = event.target.closest(".moment-delete-button");
    if (deleteButton) {
      const moment = state.moments.find((item) => Number(item.id) === Number(deleteButton.dataset.momentId));
      if (!moment || !window.confirm(`确定删除团队时刻“${moment.title}”吗？可在回收站恢复。`)) return;
      api(`/api/team-moments/${moment.id}`, { method: "DELETE" })
        .then((data) => {
          state.moments = data.moments || [];
          renderMomentYearFilter();
          renderMoments();
          toast(data.message || "团队时刻已删除");
        })
        .catch((error) => toast(error.message));
      return;
    }
    if (event.target.closest("[data-moment-close]") || event.target === $("#momentEditModal")) closeMomentModal();
  });
  $("#reminderBtn")?.addEventListener("click", () => {
    loadReminders().then(openReminderModal).catch((error) => toast(error.message));
  });
  $("#reminderReadAllBtn")?.addEventListener("click", () => {
    markRemindersRead([], true).catch((error) => toast(error.message));
  });
  $("#themeSelect").addEventListener("change", (event) => {
    setUiTheme(event.target.value);
    const label = event.target.selectedOptions?.[0]?.textContent || "新主题";
    toast(`已切换到 ${label}`);
  });
  $("#viewModeBtn").addEventListener("click", async () => {
    if (state.permissionPreview) {
      exitPermissionPreview();
      toast("已退出权限预览");
      return;
    }
    setViewMode(isAdminView() ? "user" : "admin");
    if (!canAccessPage(state.currentPage)) {
      switchPage(firstAccessiblePage());
    }
    applyAuthView();
    await refreshAll();
    toast(isAdminView() ? "已切换到管理视图" : "已切换到用户视图");
  });
  $("#exitPermissionPreviewBtn")?.addEventListener("click", () => {
    exitPermissionPreview();
    toast("已退出权限预览");
  });
  $("#prevMeetingMonthBtn").addEventListener("click", () => moveMeetingMonth(-1));
  $("#nextMeetingMonthBtn").addEventListener("click", () => moveMeetingMonth(1));
  $("#prevMonthBtn").addEventListener("click", () => moveMonth(-1));
  $("#nextMonthBtn").addEventListener("click", () => moveMonth(1));
  $("#prevMonthBtn2").addEventListener("click", () => moveMonth(-1));
  $("#nextMonthBtn2").addEventListener("click", () => moveMonth(1));
  $("#scoreYear")?.addEventListener("change", () => {
    loadRulesAndScores().catch((error) => toast(error.message));
  });
  $("#blackVisibilityForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    if (button) button.disabled = true;
    try {
      const settings = {
        red_black_show_black_points: form.elements.show_points.checked ? "1" : "0",
        red_black_show_black_details: form.elements.show_details.checked ? "1" : "0",
      };
      const data = await api("/api/settings", {
        method: "PATCH",
        body: JSON.stringify({ settings }),
      });
      state.settings = data.settings || state.settings;
      state.publicSettings = { ...state.publicSettings, ...settings };
      await loadRulesAndScores();
      toast("红黑榜显示设置已保存");
    } catch (error) {
      toast(error.message);
    } finally {
      if (button) button.disabled = false;
    }
  });

  bindForm("#userForm", (data) => api("/api/users", { method: "POST", body: JSON.stringify(data) }));
  bindForm("#userTypeForm", (data) => api("/api/user-types", { method: "POST", body: JSON.stringify(data) }));
  bindForm("#ruleForm", (data) => api("/api/rules", { method: "POST", body: JSON.stringify(data) }));
  bindForm("#scoreForm", (data) => api("/api/scores", { method: "POST", body: JSON.stringify(data) }));
  bindForm("#meetingGenerateForm", (data) => api("/api/meetings/bulk-generate", { method: "POST", body: JSON.stringify(data) }));
  bindForm("#morningItemForm", (data) => {
    if (state.morningReadOnly) throw new Error("历史日期只读，不能新增");
    const payload = { ...data, item_date: state.morningDate };
    if (!isAdminView()) delete payload.owner_id;
    return api("/api/morning-items", { method: "POST", body: JSON.stringify(payload) });
  });
  bindForm("#personalMorningCreateForm", (data) => {
    const payload = {
      ...data,
      status: "doing",
      item_date: iso(new Date()),
    };
    return api("/api/morning-items", { method: "POST", body: JSON.stringify(payload) });
  });
  $("#processTemplateForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const submit = form.querySelector('button[type="submit"]');
    if (submit) submit.disabled = true;
    try {
      const templateId = state.editingProcessTemplateId;
      await api(templateId ? `/api/process-templates/${templateId}` : "/api/process-templates", {
        method: templateId ? "PATCH" : "POST",
        body: JSON.stringify(processTemplatePayload(form)),
      });
      closeProcessTemplateModal();
      await loadProcesses();
      toast(templateId ? "流程模板已更新" : "流程模板已创建");
    } catch (error) {
      toast(error.message);
    } finally {
      if (submit) submit.disabled = false;
    }
  });
  $("#processTemplateItems")?.addEventListener("input", (event) => {
    if (event.target.closest("[data-process-item-title]")) refreshProcessTemplateItemOrder();
  });
  $("#processTemplateItems")?.addEventListener("change", (event) => {
    const parentSelect = event.target.closest("[data-process-item-parent]");
    if (parentSelect) {
      const row = parentSelect.closest("[data-process-template-item]");
      if (row) row.dataset.processParentKey = parentSelect.value;
      refreshProcessTemplateItemOrder();
      return;
    }
    if (event.target.closest("[data-process-item-required]")) refreshProcessTemplateItemOrder();
  });
  $("#processStartForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const submit = form.querySelector('button[type="submit"]');
    if (submit) submit.disabled = true;
    try {
      await api("/api/process-instances", {
        method: "POST",
        body: JSON.stringify(formData(form)),
      });
      state.processScope = "mine";
      state.processStatus = "active";
      closeProcessStartModal();
      await loadProcesses();
      toast("已生成个人流程");
    } catch (error) {
      toast(error.message);
    } finally {
      if (submit) submit.disabled = false;
    }
  });
  $("#processInstanceList")?.addEventListener("change", async (event) => {
    const checkbox = event.target.closest("[data-process-item-toggle]");
    if (!checkbox) return;
    checkbox.disabled = true;
    try {
      const result = await api(`/api/process-instance-items/${checkbox.dataset.processItemToggle}`, {
        method: "PATCH",
        body: JSON.stringify({
          completed: checkbox.checked,
          expected_version: Number(checkbox.dataset.processItemVersion || 1),
        }),
      });
      await loadProcesses();
      toast(result.message || (checkbox.checked ? "Checklist 已完成" : "Checklist 已恢复"));
    } catch (error) {
      checkbox.checked = !checkbox.checked;
      checkbox.disabled = false;
      toast(error.message);
      if (error.status === 409) loadProcesses().catch(() => {});
    }
  });
  bindForm("#topicTypeForm", (data) => api("/api/meeting-topic-types", { method: "POST", body: JSON.stringify(data) }));
  bindForm("#topicOptionForm", (data) => api("/api/meeting-topic-options", { method: "POST", body: JSON.stringify(data) }));
  bindForm("#linkForm", (data) => api("/api/links", { method: "POST", body: JSON.stringify(prepareLinkPayload(data)) }));
  bindForm("#linkCategoryForm", (data) => api("/api/link-categories", { method: "POST", body: JSON.stringify(data) }));
  bindForm("#machineForm", (data) => api("/api/machines", { method: "POST", body: JSON.stringify(data) }));
  bindForm("#shiftForm", (data) => {
    state.selectedShiftEndDate = data.shift_end_date || data.shift_start_date || state.selectedShiftDate;
    return api("/api/shifts", { method: "POST", body: JSON.stringify(data) });
  });
  bindForm("#thankForm", (_, form) => api("/api/thank-you", { method: "POST", body: JSON.stringify(thankFormPayload(form)) }));
  $("#teamChatForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const submit = form.querySelector('button[type="submit"]');
    if (submit) submit.disabled = true;
    try {
      const editingId = state.editingForumPostId;
      const data = await api(editingId ? `/api/team-posts/${editingId}` : "/api/team-posts", {
        method: editingId ? "PATCH" : "POST",
        body: JSON.stringify(formData(form)),
      });
      renderTeamChat(data.posts);
      closeForumCreateModal();
      toast(editingId ? "讨论已更新" : "讨论已发布");
    } catch (error) {
      toast(error.message);
    } finally {
      if (submit) submit.disabled = false;
    }
  });
  bindForm("#settingsForm", (data) => api("/api/settings", { method: "PATCH", body: JSON.stringify({ settings: data }) }));
  $("#settingsForm")?.addEventListener("input", (event) => {
    if (!event.target.name?.startsWith("sso_")) return;
    updateSsoModeFields();
    const persisted = $("#ssoPersistedState");
    if (persisted) {
      persisted.classList.remove("is-saved");
      persisted.innerHTML = "<strong>有未保存的 SSO 改动</strong><span>诊断只读取数据库中的已保存配置</span>";
    }
  });
  $("#ssoDiagnosticForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const submit = form.querySelector('button[type="submit"]');
    if (submit) submit.disabled = true;
    try {
      await runSsoDiagnostic(form.elements.access_token.value.trim());
      form.elements.access_token.value = "";
    } catch (error) {
      const target = $("#ssoDiagnosticResult");
      if (target) target.innerHTML = `<div class="sso-diagnostic-status sso-diagnostic-mapping_failed"><strong>诊断失败</strong><span>${escapeHtml(error.message)}</span></div>`;
    } finally {
      if (submit) submit.disabled = false;
    }
  });
  bindForm("#manualBackupForm", () => api("/api/backups", { method: "POST", body: "{}" }));

  [$("#meetingForm"), $("#meetingCreateForm")].filter(Boolean).forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await createMeetingFromForm(event.currentTarget);
      } catch (error) {
        toast(error.message);
      }
    });
  });

  $("#meetingEmailForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    submit.textContent = "正在生成";
    try {
      await openMeetingEmail(form.elements.meeting_id.value, Boolean(form.elements.include_thanks.checked));
      closeMeetingEmailModal();
    } catch (error) {
      toast(error.message);
    } finally {
      submit.disabled = false;
      submit.textContent = "生成邮件";
    }
  });

  $("#meetingAgendaPickerForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const items = $$(".meeting-agenda-option", form).map((row) => {
      const checkbox = $(".meeting-agenda-option-check", row);
      if (!checkbox?.checked) return null;
      return {
        option_id: Number(checkbox.value),
        owner_id: $(".meeting-agenda-owner", row)?.value || null,
      };
    }).filter(Boolean);
    if (!items.length) return toast("请至少勾选一个预设议题");
    const submit = $("#meetingAgendaSubmitBtn");
    submit.disabled = true;
    submit.textContent = "正在加入";
    try {
      const response = await api(`/api/meetings/${form.elements.meeting_id.value}/agenda-options`, {
        method: "POST",
        body: JSON.stringify({ items }),
      });
      state.meetings = response.meetings || state.meetings;
      closeMeetingAgendaModal();
      const current = state.meetings.find((meeting) => Number(meeting.id) === Number(state.selectedMeetingId));
      renderMeetingCalendar(state.meetings);
      renderMeetingList(state.meetings);
      renderMeetingDetail(current || null);
      toast(response.message || "议题已加入");
    } catch (error) {
      toast(error.message);
      updateMeetingAgendaSelection();
    } finally {
      submit.textContent = "加入本场会议";
    }
  });

  $("#meetingAgendaPickerForm")?.addEventListener("change", (event) => {
    const groupToggle = event.target.closest(".meeting-agenda-group-check");
    if (groupToggle) {
      $$(".meeting-agenda-option-check:not(:disabled)", groupToggle.closest(".meeting-agenda-group"))
        .forEach((checkbox) => { checkbox.checked = groupToggle.checked; });
    }
    if (event.target.closest(".meeting-agenda-option-check, .meeting-agenda-group-check")) {
      updateMeetingAgendaSelection();
    }
  });

  $("#meetingAgendaSearch")?.addEventListener("input", (event) => {
    const query = event.target.value.trim().toLowerCase();
    $$(".meeting-agenda-group", $("#meetingAgendaPickerList")).forEach((group) => {
      let visibleOptions = 0;
      $$(".meeting-agenda-option", group).forEach((row) => {
        const visible = !query || row.dataset.search.includes(query);
        row.classList.toggle("hidden", !visible);
        if (visible) visibleOptions += 1;
      });
      group.classList.toggle("hidden", visibleOptions === 0);
    });
  });
  $("#archiveSearchForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await searchArchive(event.currentTarget);
    } catch (error) {
      toast(error.message);
    }
  });
  $("#archiveRefreshBtn")?.addEventListener("click", () => {
    loadArchive().then(() => toast("归档已刷新")).catch((error) => toast(error.message));
  });

  $("#linkCategoryFilter").addEventListener("change", renderLinks);
  $("#linkStatusFilter").addEventListener("change", renderLinks);
  $("#linkKeywordSearch").addEventListener("input", renderLinks);
  $("#morningDate")?.addEventListener("change", async (event) => {
    state.morningDate = event.target.value || iso(new Date());
    await loadMorning().catch((error) => toast(error.message));
  });
  $("#morningOwnerFilter")?.addEventListener("change", () => {
    renderMorningBoard();
    renderMorningNavigator();
  });
  $("#morningStatusFilter")?.addEventListener("change", () => {
    renderMorningBoard();
    renderMorningNavigator();
  });
  $("#morningRefreshBtn")?.addEventListener("click", () => {
    loadMorning({ preserveScroll: true })
      .then(() => toast("早例会已刷新"))
      .catch((error) => toast(error.message));
  });
  $("#dashboardUserSelect")?.addEventListener("change", (event) => {
    state.dashboardUserId = Number(event.target.value) || state.user?.id || null;
    state.activePersonalMorningChain = null;
    loadDashboard().catch((error) => toast(error.message));
  });
  $("#thankPeriodControls")?.addEventListener("change", (event) => {
    if (event.target.matches("#thankYearSelect")) {
      state.thankYear = Number(event.target.value) || state.thankYear;
      loadThanks().catch((error) => toast(error.message));
    }
    if (event.target.matches("#thankMonthSelect")) {
      if (event.target.value === "year") {
        state.thankScope = "year";
      } else {
        state.thankScope = "month";
        state.thankMonth = Number(event.target.value) || state.thankMonth;
      }
      loadThanks().catch((error) => toast(error.message));
    }
  });
  const linkForm = $("#linkForm");
  if (linkForm) {
    ["title", "url", "description"].forEach((name) => {
      linkForm.elements[name]?.addEventListener("input", () => applyLinkKeywordSuggestion(linkForm));
    });
    linkForm.elements.category?.addEventListener("change", () => applyLinkKeywordSuggestion(linkForm));
    ["machine_scope", "process_tags"].forEach((name) => {
      linkForm.elements[name]?.addEventListener("input", () => {
        linkForm.elements[name].dataset.autoSuggested = "0";
      });
    });
    $("#inferLinkScopeBtn")?.addEventListener("click", () => {
      applyLinkKeywordSuggestion(linkForm, true);
      toast("已根据链接内容提炼关键词");
    });
  }

  const memberForm = $("#memberForm");
  if (memberForm) {
    memberForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await submitMemberForm(event.currentTarget);
        event.currentTarget.reset();
        await refreshAll();
        toast("成员已保存");
      } catch (error) {
        toast(error.message);
      }
    });
  }

  $("#forumSearchInput")?.addEventListener("input", (event) => {
    state.forumSearch = event.target.value || "";
    state.forumPage = 1;
    renderForumTopics();
  });
  $("#forumSortSelect")?.addEventListener("change", (event) => {
    state.forumSort = event.target.value || "recent";
    state.forumPage = 1;
    renderForumTopics();
  });
  $("#teamChatForm")?.elements.content?.addEventListener("input", (event) => {
    $("#forumContentCount").textContent = `${event.target.value.length} / 2000`;
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeMomentGallery();
      closePasswordModal();
      closeUserTypePermissionModal();
      closeUserAccountModal();
      closeMemberEditModal();
      closeMorningHistoryModal();
      closeProcessTemplateModal();
      closeProcessStartModal();
      closeMeetingMinuteModal();
      closeMeetingAgendaModal();
      closeMeetingAttendanceModal();
      closeMeetingCreateModal();
      closeMeetingEmailModal();
      closeMemberScoreModal();
      closeLinkEditModal();
      closeLinkDeleteModal();
      closeLinkActionMenus();
      closeReminderModal();
      closeForumCreateModal();
      closeForumDetailModal();
      closeSsoDiagnosticModal();
      closeShiftPopover();
      return;
    }
    if (!$("#momentGalleryModal")?.classList.contains("hidden") && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
      event.preventDefault();
      moveMomentGallery(event.key === "ArrowLeft" ? -1 : 1);
      return;
    }
    const shiftDay = event.target.closest?.(".shift-day");
    if (shiftDay && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      selectShiftDay(shiftDay);
    }
    const personalDoneItem = event.target.closest?.("[data-personal-calendar-focus]");
    if (personalDoneItem && !event.target.closest("button, input, select, textarea, label, a") && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      focusPersonalMorningChain(personalDoneItem.dataset.personalCalendarFocus);
    }
    const forumTopic = event.target.closest?.("[data-forum-post-id]");
    if (forumTopic && !event.target.closest("button, input, select, textarea, label, a") && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      openForumDetail(forumTopic.dataset.forumPostId).catch((error) => toast(error.message));
    }
  });

  document.body.addEventListener("click", (event) => {
    if (event.target.closest("#ssoOneAccessPresetBtn")) {
      applyOneAccessPreset();
      return;
    }
    if (event.target.closest("#ssoDiagnoseBtn")) {
      openSsoDiagnosticModal();
      return;
    }
    if (event.target.closest("[data-sso-diagnostic-close]") || event.target === $("#ssoDiagnosticModal")) {
      closeSsoDiagnosticModal();
      return;
    }
    if (event.target.closest("#openProcessTemplateBtn")) {
      openProcessTemplateModal();
      return;
    }
    if (event.target.closest("[data-process-template-close]") || event.target === $("#processTemplateModal")) {
      closeProcessTemplateModal();
      return;
    }
    if (event.target.closest("[data-process-start-close]") || event.target === $("#processStartModal")) {
      closeProcessStartModal();
      return;
    }
    const mindmapNode = event.target.closest("[data-process-mindmap-select]");
    if (mindmapNode) {
      selectProcessTemplateItem(mindmapNode.dataset.processMindmapSelect, true);
      return;
    }
    if (event.target.closest("#addProcessTemplateItemBtn")) {
      appendProcessTemplateItem(state.selectedProcessTemplateItemKey || "");
      return;
    }
    if (event.target.closest("#addProcessRootItemBtn")) {
      appendProcessTemplateItem("");
      return;
    }
    const processItemRemove = event.target.closest("[data-process-item-remove]");
    if (processItemRemove) {
      const rows = $$("#processTemplateItems [data-process-template-item]");
      if (rows.length <= 1) return toast("流程模板至少需要一个 Checklist");
      const row = processItemRemove.closest("[data-process-template-item]");
      const parentKey = row?.dataset.processParentKey || "";
      const fallback = rows.find((candidate) => candidate.dataset.processItemKey === parentKey)
        || row?.previousElementSibling
        || row?.nextElementSibling;
      row?.remove();
      state.selectedProcessTemplateItemKey = fallback?.dataset.processItemKey || null;
      refreshProcessTemplateItemOrder();
      return;
    }
    const processItemMove = event.target.closest("[data-process-item-move]");
    if (processItemMove) {
      const row = processItemMove.closest("[data-process-template-item]");
      const direction = Number(processItemMove.dataset.processItemMove || 0);
      const sibling = direction < 0 ? row?.previousElementSibling : row?.nextElementSibling;
      if (row && sibling) {
        if (direction < 0) row.parentElement.insertBefore(row, sibling);
        else row.parentElement.insertBefore(sibling, row);
        refreshProcessTemplateItemOrder();
      }
      return;
    }
    const processTemplateEdit = event.target.closest("[data-process-template-edit]");
    if (processTemplateEdit) {
      openProcessTemplateModal(processTemplateEdit.dataset.processTemplateEdit);
      return;
    }
    const processTemplateGraph = event.target.closest("[data-process-template-graph]");
    if (processTemplateGraph) {
      state.selectedProcessTemplateGraphId = Number(processTemplateGraph.dataset.processTemplateGraph);
      renderProcessTemplates();
      $("#processTemplateGraph")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return;
    }
    const processTemplateDelete = event.target.closest("[data-process-template-delete]");
    if (processTemplateDelete) {
      const name = processTemplateDelete.dataset.processTemplateName || "该流程模板";
      if (!window.confirm(`确定停用“${name}”吗？已经生成的个人流程会继续保留。`)) return;
      api(`/api/process-templates/${processTemplateDelete.dataset.processTemplateDelete}`, { method: "DELETE" })
        .then(loadProcesses)
        .then(() => toast("流程模板已停用"))
        .catch((error) => toast(error.message));
      return;
    }
    const processStart = event.target.closest("[data-process-start]");
    if (processStart) {
      openProcessStartModal(processStart.dataset.processStart);
      return;
    }
    const processScope = event.target.closest("[data-process-scope]");
    if (processScope) {
      state.processScope = processScope.dataset.processScope || "mine";
      loadProcesses().catch((error) => toast(error.message));
      return;
    }
    const processStatus = event.target.closest("[data-process-status]");
    if (processStatus) {
      state.processStatus = processStatus.dataset.processStatus || "active";
      loadProcesses().catch((error) => toast(error.message));
      return;
    }
    const processInstanceView = event.target.closest("[data-process-instance-view]");
    if (processInstanceView) {
      state.processInstanceViews[processInstanceView.dataset.processInstanceView] = processInstanceView.dataset.processView || "graph";
      renderProcessInstances();
      return;
    }
    const processInstanceDelete = event.target.closest("[data-process-instance-delete]");
    if (processInstanceDelete) {
      const name = processInstanceDelete.dataset.processInstanceName || "该流程";
      if (!window.confirm(`确定取消“${name}”吗？取消后将从流程列表隐藏。`)) return;
      api(`/api/process-instances/${processInstanceDelete.dataset.processInstanceDelete}`, { method: "DELETE" })
        .then(loadProcesses)
        .then(() => toast("流程已取消"))
        .catch((error) => toast(error.message));
      return;
    }
    if (event.target.closest("#orgUnitCreateBtn")) {
      openOrgUnitModal();
      return;
    }
    const orgEdit = event.target.closest(".org-unit-edit-btn");
    if (orgEdit) {
      openOrgUnitModal(orgEdit.dataset.orgUnitId);
      return;
    }
    const orgDelete = event.target.closest(".org-unit-delete-btn");
    if (orgDelete) {
      if (!window.confirm(`确定删除团队“${orgDelete.dataset.orgUnitName}”吗？仅无下级且无成员时可以删除。`)) return;
      api(`/api/org-units/${orgDelete.dataset.orgUnitId}`, { method: "DELETE" })
        .then(() => loadUsers())
        .then(() => toast("团队层级已删除"))
        .catch((error) => toast(error.message));
      return;
    }
    if (event.target.closest("[data-org-unit-modal-close]") || event.target === $("#orgUnitModal")) {
      closeOrgUnitModal();
      return;
    }
    if (event.target.closest("#forumCreateButton, [data-forum-create-open]")) {
      openForumCreateModal();
      return;
    }
    if (event.target.closest("[data-forum-create-close]") || event.target === $("#forumCreateModal")) {
      closeForumCreateModal();
      return;
    }
    if (event.target.closest("[data-forum-detail-close]") || event.target === $("#forumDetailModal")) {
      closeForumDetailModal();
      return;
    }
    const forumCategoryTab = event.target.closest("[data-forum-category]");
    if (forumCategoryTab) {
      state.forumCategory = forumCategoryTab.dataset.forumCategory || "all";
      state.forumPage = 1;
      $$("[data-forum-category]").forEach((button) => {
        const active = button === forumCategoryTab;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", String(active));
      });
      renderForumTopics();
      return;
    }
    if (event.target.closest("#forumMineButton")) {
      state.forumMineOnly = !state.forumMineOnly;
      state.forumPage = 1;
      $("#forumMineButton").classList.toggle("active", state.forumMineOnly);
      $("#forumMineButton").setAttribute("aria-pressed", String(state.forumMineOnly));
      renderForumTopics();
      return;
    }
    const forumPageButton = event.target.closest("[data-forum-page]");
    if (forumPageButton && !forumPageButton.disabled) {
      state.forumPage = Number(forumPageButton.dataset.forumPage) || 1;
      renderForumTopics();
      return;
    }
    const forumStatusToggle = event.target.closest(".forum-status-toggle");
    if (forumStatusToggle) {
      updateForumPost(forumStatusToggle.dataset.postId, { status: forumStatusToggle.dataset.nextStatus }).catch((error) => toast(error.message));
      return;
    }
    const forumPinToggle = event.target.closest(".forum-pin-toggle");
    if (forumPinToggle) {
      updateForumPost(forumPinToggle.dataset.postId, { pinned: forumPinToggle.dataset.nextPinned === "1" }).catch((error) => toast(error.message));
      return;
    }
    const forumEditPost = event.target.closest(".forum-edit-post");
    if (forumEditPost) {
      const post = state.teamPosts.find((item) => Number(item.id) === Number(forumEditPost.dataset.postId));
      if (!post) return toast("讨论主题已更新，请刷新后重试");
      closeForumDetailModal();
      openForumCreateModal(post);
      return;
    }
    const forumDeletePost = event.target.closest(".forum-delete-post");
    if (forumDeletePost) {
      if (!window.confirm(`确定删除“${forumDeletePost.dataset.postTitle || "该讨论"}”吗？主题和回复将从讨论区隐藏，可由管理员在回收站恢复。`)) return;
      api(`/api/team-posts/${forumDeletePost.dataset.postId}`, { method: "DELETE" })
        .then((data) => {
          closeForumDetailModal();
          renderTeamChat(data.posts);
          toast("讨论主题已删除");
        })
        .catch((error) => toast(error.message));
      return;
    }
    const forumTopic = event.target.closest("[data-forum-post-id]");
    if (forumTopic && (forumTopic.matches("button") || !event.target.closest("button, input, select, textarea, label, a"))) {
      openForumDetail(forumTopic.dataset.forumPostId).catch((error) => toast(error.message));
      return;
    }
    const scoreMemberButton = event.target.closest("[data-score-user-id]");
    if (scoreMemberButton) {
      openMemberScoreModal(scoreMemberButton.dataset.scoreUserId, scoreMemberButton.dataset.scoreUserName)
        .catch((error) => toast(error.message));
      return;
    }
    const userTypeConfig = event.target.closest(".user-type-config-btn");
    if (userTypeConfig) {
      openUserTypePermissionModal(userTypeConfig.dataset.typeKey);
      return;
    }
    const userAccountEdit = event.target.closest(".user-account-edit-btn");
    if (userAccountEdit) {
      openUserAccountModal(userAccountEdit.dataset.userId);
      return;
    }
    if (event.target.closest("[data-user-type-modal-close]") || event.target === $("#userTypePermissionModal")) {
      closeUserTypePermissionModal();
      return;
    }
    if (event.target.closest("[data-user-account-modal-close]") || event.target === $("#userAccountModal")) {
      closeUserAccountModal();
      return;
    }
    const useSuggestedOrg = event.target.closest("#userUseSuggestedOrgBtn");
    if (useSuggestedOrg) {
      const suggestedOrgId = String(useSuggestedOrg.dataset.orgUnitId || "");
      const form = $("#userAccountEditForm");
      if (suggestedOrgId && form?.elements.org_unit_id) {
        form.elements.org_unit_id.value = suggestedOrgId;
        toast("已填入 SSO 建议团队，保存账号后生效");
      }
      return;
    }
    if (event.target.closest("#userBulkClearBtn")) {
      clearUserBulkSelection();
      return;
    }
    if (event.target.closest("#userBulkExecuteBtn")) {
      const userIds = selectedBulkUserIds();
      if (!userIds.length) return toast("请先选择账号");
      const action = $("#userBulkAction")?.value || "";
      const targetValue = $("#userBulkTarget")?.value || "";
      let request;
      let confirmMessage;
      let successMessage;
      if (action === "type") {
        if (!targetValue) return toast("请选择目标用户类型");
        const targetName = state.userTypes.find((type) => type.key === targetValue)?.name || "目标类型";
        confirmMessage = `确定将 ${userIds.length} 个账号批量调整为“${targetName}”吗？`;
        successMessage = `已批量调整 ${userIds.length} 个账号的用户类型`;
        request = () => api("/api/users/bulk-type", { method: "PATCH", body: JSON.stringify({ user_ids: userIds, user_type: targetValue }) });
      } else if (action === "org") {
        const orgUnitId = Number(targetValue || 0);
        if (!orgUnitId) return toast("请选择目标团队");
        const target = state.orgUnits.find((unit) => Number(unit.id) === orgUnitId);
        confirmMessage = `确定将 ${userIds.length} 个账号批量调整到“${target?.name || "目标团队"}”吗？`;
        successMessage = `已批量调整 ${userIds.length} 个账号的所属团队`;
        request = () => api("/api/users/bulk-org", { method: "PATCH", body: JSON.stringify({ user_ids: userIds, org_unit_id: orgUnitId }) });
      } else if (action === "suggested-org") {
        const suggestedCount = userIds.filter((id) => state.users.find((user) => Number(user.id) === id)?.suggested_org_unit_id).length;
        if (!suggestedCount) return toast("所选账号没有 SSO 建议团队");
        confirmMessage = `确定采用 ${suggestedCount} 个账号的 SSO 建议团队吗？没有建议的账号将跳过。`;
        successMessage = `已采用所选账号的 SSO 建议团队`;
        request = () => api("/api/users/bulk-suggested-org", { method: "PATCH", body: JSON.stringify({ user_ids: userIds }) });
      } else if (action === "delete") {
        const names = userIds.map((id) => state.users.find((user) => Number(user.id) === id)?.display_name).filter(Boolean);
        const preview = names.slice(0, 3).join("、") + (names.length > 3 ? ` 等 ${names.length} 人` : "");
        confirmMessage = `确定删除 ${preview || `${userIds.length} 个账号`}吗？账号将无法登录，历史记录保留，并可由管理员从回收站恢复。`;
        successMessage = `已删除 ${userIds.length} 个账号`;
        request = () => api("/api/users/bulk-delete", { method: "DELETE", body: JSON.stringify({ user_ids: userIds }) });
      } else {
        return toast("请选择批量操作");
      }
      if (!window.confirm(confirmMessage)) return;
      const button = $("#userBulkExecuteBtn");
      if (button) button.disabled = true;
      request()
        .then(() => {
          state.thankUsers = [];
          return loadUsers();
        })
        .then(() => toast(successMessage))
        .catch((error) => toast(error.message))
        .finally(() => { if (button) button.disabled = false; });
      return;
    }
    const permissionPreview = event.target.closest(".permission-preview-btn");
    if (permissionPreview) {
      const form = permissionPreview.closest(".user-type-permission-form");
      if (form) closeUserTypePermissionModal();
      enterPermissionPreview(
        permissionPreview.dataset.typeKey,
        form ? permissionFormPermissions(form) : null,
        form?.elements.name?.value || "",
      );
      return;
    }
    const permissionImpact = event.target.closest(".permission-impact-btn");
    if (permissionImpact) {
      const form = permissionImpact.closest(".user-type-permission-form");
      assessPermissionImpact(form).catch((error) => toast(error.message));
      return;
    }
    const sessionRevoke = event.target.closest(".session-revoke-btn");
    if (sessionRevoke) {
      const current = sessionRevoke.closest(".session-row")?.classList.contains("current");
      if (!window.confirm(current ? "确定退出当前设备吗？" : "确定撤销这个登录设备吗？")) return;
      api(`/api/sessions/${sessionRevoke.dataset.sessionId}`, { method: "DELETE" })
        .then((data) => {
          if (data.current_revoked) {
            closePasswordModal();
            return transitionToLoggedOut(true, true);
          }
          return loadSessions();
        })
        .then(() => toast("登录会话已撤销"))
        .catch((error) => toast(error.message));
      return;
    }
    const permissionCheckbox = event.target.closest("[data-permission-action]");
    if (permissionCheckbox) {
      const form = permissionCheckbox.closest(".user-type-permission-form");
      const moduleKey = permissionCheckbox.dataset.permissionModule;
      if (permissionCheckbox.checked && permissionCheckbox.dataset.permissionAction !== "view") {
        const viewCheckbox = $(`[data-permission-module="${moduleKey}"][data-permission-action="view"]`, form);
        if (viewCheckbox) viewCheckbox.checked = true;
      }
      if (!permissionCheckbox.checked && permissionCheckbox.dataset.permissionAction === "view") {
        $$(`[data-permission-module="${moduleKey}"]`, form).forEach((input) => { input.checked = false; });
      }
      const impact = form.querySelector("[data-permission-impact]");
      if (impact) impact.innerHTML = "<strong>配置已调整</strong><span>点击“评估变更影响”查看受影响账号和权限项</span>";
      return;
    }
    if (event.target.closest("[data-reminder-close]") || event.target === $("#reminderModal")) {
      closeReminderModal();
      return;
    }
    const reminderItem = event.target.closest("[data-reminder-key]");
    if (reminderItem) {
      const page = reminderItem.dataset.reminderPage;
      markRemindersRead([reminderItem.dataset.reminderKey])
        .then(() => {
          closeReminderModal();
          switchPage(page);
          return refreshPageData(page);
        })
        .catch((error) => toast(error.message));
      return;
    }
    const archiveYear = event.target.closest("[data-archive-year]");
    if (archiveYear) {
      const form = $("#archiveSearchForm");
      if (form) {
        form.elements.year.value = archiveYear.dataset.archiveYear || "";
        searchArchive(form).catch((error) => toast(error.message));
      }
      return;
    }
    const backupVerify = event.target.closest(".backup-verify-btn");
    if (backupVerify) {
      api("/api/backups/verify", {
        method: "POST",
        body: JSON.stringify({ filename: backupVerify.dataset.backupFile }),
      })
        .then((data) => {
          state.backups = data.backups || state.backups;
          renderBackups();
          toast(data.message || "备份校验完成");
        })
        .catch((error) => toast(error.message));
      return;
    }
    const backupRestore = event.target.closest(".backup-restore-btn");
    if (backupRestore) {
      const filename = backupRestore.dataset.backupFile || "";
      if (!window.confirm(`确定恢复到备份「${filename}」吗？系统会先生成恢复前备份，然后覆盖当前数据库。`)) return;
      api("/api/backups/restore", {
        method: "POST",
        body: JSON.stringify({ filename }),
      })
        .then((data) => {
          state.backups = data.backups || state.backups;
          renderBackups();
          toast(data.message || "数据库已恢复");
          return refreshAll();
        })
        .catch((error) => toast(error.message));
      return;
    }
    const recycleRestore = event.target.closest(".recycle-restore-btn");
    if (recycleRestore) {
      api(`/api/recycle-bin/${recycleRestore.dataset.recycleId}/restore`, { method: "POST" })
        .then((data) => {
          state.recycleBin = data.items || [];
          renderRecycleBin();
          return refreshAll();
        })
        .then(() => toast("内容已恢复"))
        .catch((error) => toast(error.message));
      return;
    }
    const recyclePurge = event.target.closest(".recycle-purge-btn");
    if (recyclePurge) {
      if (!window.confirm(`确定彻底删除「${recyclePurge.dataset.recycleTitle || "该内容"}」吗？此操作无法恢复。`)) return;
      api(`/api/recycle-bin/${recyclePurge.dataset.recycleId}`, { method: "DELETE" })
        .then((data) => {
          state.recycleBin = data.items || [];
          renderRecycleBin();
          toast("内容已彻底删除");
        })
        .catch((error) => toast(error.message));
      return;
    }
    if (!event.target.closest("#shiftCalendar")) {
      closeShiftPopover();
    }
    const activeThankPicker = event.target.closest(".thank-recipient-picker");
    $$(".thank-recipient-picker[open]").forEach((picker) => {
      if (picker !== activeThankPicker) picker.removeAttribute("open");
    });
    if (!event.target.closest(".link-action-menu-wrap")) {
      closeLinkActionMenus();
    }
    const memberEditButton = event.target.closest(".member-edit-btn");
    if (memberEditButton) {
      openMemberEditModal(memberEditButton.dataset.memberId);
      return;
    }
    const memberOrderButton = event.target.closest(".member-order-btn");
    if (memberOrderButton && !memberOrderButton.disabled) {
      moveMemberCard(memberOrderButton.dataset.memberId, memberOrderButton.dataset.orderDirection)
        .catch((error) => toast(error.message));
      return;
    }
    if (event.target.closest("[data-member-modal-close]") || event.target === $("#memberEditModal")) {
      closeMemberEditModal();
      return;
    }
    if (event.target.closest("[data-password-modal-close]") || event.target === $("#passwordModal")) {
      closePasswordModal();
      return;
    }
    if (event.target.closest("[data-morning-history-close]") || event.target === $("#morningHistoryModal")) {
      closeMorningHistoryModal();
      return;
    }
    if (event.target.closest("[data-meeting-minute-close]") || event.target === $("#meetingMinuteModal")) {
      closeMeetingMinuteModal();
      return;
    }
    if (event.target.closest("[data-meeting-agenda-close]") || event.target === $("#meetingAgendaModal")) {
      closeMeetingAgendaModal();
      return;
    }
    if (event.target.closest("[data-meeting-attendance-close]") || event.target === $("#meetingAttendanceModal")) {
      closeMeetingAttendanceModal();
      return;
    }
    if (event.target.closest("[data-meeting-create-close]") || event.target === $("#meetingCreateModal")) {
      closeMeetingCreateModal();
      return;
    }
    if (event.target.closest("[data-meeting-email-close]") || event.target === $("#meetingEmailModal")) {
      closeMeetingEmailModal();
      return;
    }
    if (event.target.closest("[data-member-score-close]") || event.target === $("#memberScoreModal")) {
      closeMemberScoreModal();
      return;
    }
    if (event.target.closest("#openMeetingCreateBtn")) {
      openMeetingCreateModal();
      return;
    }
    const meetingAgendaPicker = event.target.closest(".meeting-agenda-picker-btn");
    if (meetingAgendaPicker) {
      openMeetingAgendaModal(meetingAgendaPicker.dataset.meetingId);
      return;
    }
    const meetingAttendance = event.target.closest(".meeting-attendance-btn");
    if (meetingAttendance) {
      openMeetingAttendanceModal(meetingAttendance.dataset.meetingId);
      return;
    }
    if (event.target.closest("[data-link-edit-close]") || event.target === $("#linkEditModal")) {
      closeLinkEditModal();
      return;
    }
    if (event.target.closest("[data-link-delete-close]") || event.target === $("#linkDeleteModal")) {
      closeLinkDeleteModal();
      return;
    }
    if (event.target.closest("[data-link-delete-confirm]")) {
      if (pendingLinkDeleteId) {
        deleteLink(pendingLinkDeleteId).catch((error) => toast(error.message));
      }
      return;
    }
    const linkMenuToggle = event.target.closest("[data-link-menu-toggle]");
    if (linkMenuToggle) {
      toggleLinkActionMenu(linkMenuToggle);
      return;
    }
    const linkEditButton = event.target.closest(".link-edit-btn");
    if (linkEditButton) {
      openLinkEditModal(linkEditButton.dataset.linkId);
      return;
    }
    const linkDeleteButton = event.target.closest(".link-delete-btn");
    if (linkDeleteButton) {
      openLinkDeleteModal(linkDeleteButton.dataset.linkId);
      return;
    }
    const meetingMinuteButton = event.target.closest(".meeting-minute-btn");
    if (meetingMinuteButton) {
      openMeetingMinuteModal(meetingMinuteButton.dataset.itemId);
      return;
    }
    const meetingQuickNote = event.target.closest(".meeting-quick-note-btn");
    if (meetingQuickNote) {
      openMeetingMinuteModal(meetingQuickNote.dataset.itemId, meetingQuickNote.dataset.noteMode);
      return;
    }
    const meetingCarry = event.target.closest(".meeting-carry-btn");
    if (meetingCarry) {
      if (!window.confirm("将该议题顺延到下一场会议吗？当前会议记录会保留。")) return;
      api(`/api/meeting-items/${meetingCarry.dataset.itemId}/carry-forward`, { method: "POST" })
        .then((data) => { state.meetings = data.meetings || state.meetings; return loadMeetings(); })
        .then(() => toast("议题已顺延到下一场会议"))
        .catch((error) => toast(error.message));
      return;
    }
    const meetingStatus = event.target.closest(".meeting-flow-step[data-meeting-status]");
    if (meetingStatus && !meetingStatus.disabled) {
      updateMeetingStatus(meetingStatus.dataset.meetingId, meetingStatus.dataset.meetingStatus).catch((error) => toast(error.message));
      return;
    }
    const meetingCopyAgenda = event.target.closest(".meeting-copy-agenda-btn");
    if (meetingCopyAgenda) {
      if (!window.confirm("沿用最近一场同名会议的议题和会前准备信息吗？重复标题会自动跳过。")) return;
      api(`/api/meetings/${meetingCopyAgenda.dataset.meetingId}/copy-agenda`, { method: "POST" })
        .then((data) => { state.meetings = data.meetings || state.meetings; return loadMeetings(); })
        .then(() => toast("已沿用上场会议议题"))
        .catch((error) => toast(error.message));
      return;
    }
    const meetingItemDelete = event.target.closest(".meeting-item-delete-btn");
    if (meetingItemDelete) {
      if (!window.confirm(`确定删除议题「${meetingItemDelete.dataset.itemTitle || "该议题"}」吗？删除后可在回收站恢复。`)) return;
      api(`/api/meeting-items/${meetingItemDelete.dataset.itemId}`, { method: "DELETE" })
        .then((data) => {
          state.meetings = data.meetings || state.meetings;
          return loadMeetings();
        })
        .then(() => toast("议题已移入回收站"))
        .catch((error) => toast(error.message));
      return;
    }
    const morningHistoryButton = event.target.closest(".morning-history-btn");
    if (morningHistoryButton) {
      openMorningHistory(morningHistoryButton.dataset.morningHistoryId).catch((error) => {
        closeMorningHistoryModal();
        toast(error.message);
      });
      return;
    }
    const morningOwnerTarget = event.target.closest("[data-morning-owner-target]");
    if (morningOwnerTarget) {
      const target = document.getElementById(`morning-owner-${morningOwnerTarget.dataset.morningOwnerTarget}`);
      target?.scrollIntoView({ behavior: "smooth", block: "start" });
      target?.classList.add("is-navigated");
      window.setTimeout(() => target?.classList.remove("is-navigated"), 1400);
      return;
    }
    const morningOrder = event.target.closest("[data-morning-order-user]");
    if (morningOrder) {
      moveMorningUser(morningOrder.dataset.morningOrderUser, morningOrder.dataset.morningOrderDirection)
        .catch((error) => toast(error.message));
      return;
    }
    const morningHistoryRow = event.target.closest(".morning-list-item[data-morning-history-id]");
    if (morningHistoryRow && !event.target.closest("button, input, textarea, select, label, form")) {
      openMorningHistory(morningHistoryRow.dataset.morningHistoryId).catch((error) => {
        closeMorningHistoryModal();
        toast(error.message);
      });
      return;
    }
    const attendanceStatus = event.target.closest(".attendance-status-btn");
    if (attendanceStatus) {
      const form = attendanceStatus.closest(".attendance-row");
      form.elements.status.value = attendanceStatus.dataset.attendanceStatus;
      $$(".attendance-status-btn", form).forEach((button) => button.classList.toggle("active", button === attendanceStatus));
      updateAttendanceDonationVisibility(form);
      saveAttendanceForm(form).catch((error) => toast(error.message));
      return;
    }
    const reactionToggle = event.target.closest(".chat-reaction-picker-toggle");
    if (reactionToggle) {
      openReactionPopover(reactionToggle);
      return;
    }
    const chatReaction = event.target.closest(".chat-reaction-option, .chat-reaction-chip");
    if (chatReaction) {
      const targetType = chatReaction.dataset.reactionTarget || activeReactionTarget?.type;
      const targetId = chatReaction.dataset.reactionId || activeReactionTarget?.id;
      sendTeamReaction(targetType, targetId, chatReaction.dataset.reaction).catch((error) => toast(error.message));
      return;
    }
    if (event.target.closest("#teamReactionPopover")) {
      return;
    }
    if (!event.target.closest(".chat-reaction-wrap")) {
      closeReactionPopover();
    }
    const rulePick = event.target.closest(".rule-pick-btn");
    if (rulePick) {
      selectScoreRule(rulePick.dataset.ruleId);
      return;
    }
    const morningChoice = event.target.closest(".morning-choice-btn");
    if (morningChoice) {
      setMorningChoice(morningChoice);
      return;
    }
    const personalDoneFocus = event.target.closest("[data-personal-calendar-focus]");
    if (personalDoneFocus && !event.target.closest("button, input, select, textarea, label, a")) {
      focusPersonalMorningChain(personalDoneFocus.dataset.personalCalendarFocus);
      return;
    }
    const meetingListScope = event.target.closest("[data-meeting-list-scope]");
    if (meetingListScope) {
      setMeetingListScope(meetingListScope.dataset.meetingListScope);
      return;
    }
    if (event.target.closest(".clear-score-rule-btn")) {
      const form = $("#scoreForm");
      if (form) form.elements.rule_id.value = "";
      renderSelectedScoreRule();
      return;
    }
    const morningDelete = event.target.closest(".morning-delete-btn");
    if (morningDelete) {
      if (state.morningReadOnly) {
        toast("历史日期只读，不能删除");
        return;
      }
      if (!window.confirm("确定删除这条早例会事项吗？")) return;
      api(`/api/morning-items/${morningDelete.dataset.itemId}`, {
        method: "DELETE",
        body: JSON.stringify({ expected_version: Number(morningDelete.dataset.itemVersion || 1) }),
      })
        .then((data) => {
          state.morningItems = data.items || state.morningItems;
          state.morningUsers = data.users || state.morningUsers;
          state.morningVersionToken = data.version_token || state.morningVersionToken;
          state.morningUpdatePending = false;
          renderMorning();
          toast("早例会事项已删除");
        })
        .catch((error) => toast(error.message));
      return;
    }
    const thankEdit = event.target.closest(".thank-edit-btn");
    if (thankEdit) {
      const evidence = window.prompt("修改感谢事实依据", thankEdit.dataset.evidence || "");
      if (evidence === null) return;
      api(`/api/thank-you/${thankEdit.dataset.voteId}`, { method: "PATCH", body: JSON.stringify({ evidence }) })
        .then(loadThanks)
        .then(() => toast("感谢记录已更新"))
        .catch((error) => toast(error.message));
      return;
    }
    const thankDelete = event.target.closest(".thank-delete-btn");
    if (thankDelete) {
      const title = thankDelete.dataset.voteTitle || "这条感谢记录";
      if (!window.confirm(`确定删除 ${title} 吗？`)) return;
      api(`/api/thank-you/${thankDelete.dataset.voteId}`, { method: "DELETE" })
        .then(loadThanks)
        .then(() => toast("感谢记录已删除"))
        .catch((error) => toast(error.message));
      return;
    }
    const chatReplyToggle = event.target.closest(".chat-reply-toggle");
    if (chatReplyToggle) {
      const actionGroup = chatReplyToggle.closest(".chat-reply-actions, .chat-reply-tools");
      const inlineForm = chatReplyToggle.nextElementSibling?.matches?.(".chat-reply-form")
        ? chatReplyToggle.nextElementSibling
        : null;
      const adjacentForm = actionGroup?.nextElementSibling?.matches?.(".chat-reply-form")
        ? actionGroup.nextElementSibling
        : null;
      const form = inlineForm || adjacentForm || actionGroup?.querySelector?.(":scope > .chat-reply-form");
      if (!form) {
        toast("回复框加载失败，请刷新页面后重试");
        return;
      }
      const willOpen = form.classList.contains("hidden");
      document.querySelectorAll(".chat-reply-form:not(.hidden)").forEach((openForm) => {
        if (openForm !== form) openForm.classList.add("hidden");
      });
      form.classList.toggle("hidden", !willOpen);
      if (willOpen) form.elements.content?.focus();
      return;
    }
    const chatReplyDelete = event.target.closest(".chat-reply-delete");
    if (chatReplyDelete) {
      if (!window.confirm("确定删除这条回复吗？其下的楼中回复也会一起删除。")) return;
      api(`/api/team-replies/${chatReplyDelete.dataset.replyId}`, { method: "DELETE" })
        .then((data) => renderTeamChat(data.posts, true))
        .then(() => toast("回复已删除"))
        .catch((error) => toast(error.message));
      return;
    }
    const deleteButton = event.target.closest(".user-delete-btn");
    const userTypeDelete = event.target.closest(".user-type-delete-btn[data-type-key]");
    if (userTypeDelete) {
      const name = userTypeDelete.dataset.typeName || "该用户类型";
      if (!window.confirm(`确定删除“${name}”吗？删除后不能再分配给新用户。`)) return;
      api(`/api/user-types/${userTypeDelete.dataset.typeKey}`, { method: "DELETE" })
        .then(loadUsers)
        .then(() => toast("用户类型已删除"))
        .catch((error) => toast(error.message));
      return;
    }
    if (deleteButton) {
      const name = deleteButton.dataset.userName || "该用户";
      if (!window.confirm(`确定删除 ${name} 吗？历史记录会保留，但该账号将无法登录。`)) return;
      api(`/api/users/${deleteButton.dataset.userId}`, { method: "DELETE" })
        .then(refreshAll)
        .then(() => toast("用户已删除"))
        .catch((error) => toast(error.message));
      return;
    }
    const presetDelete = event.target.closest(".preset-delete-btn");
    if (presetDelete) {
      if (!window.confirm("确定删除这个预设议题吗？已生成到会议里的历史议题会保留。")) return;
      api(`/api/meeting-topic-options/${presetDelete.dataset.optionId}`, { method: "DELETE" })
        .then(refreshAll)
        .then(() => toast("预设议题已删除"))
        .catch((error) => toast(error.message));
      return;
    }
    const topicTypeDelete = event.target.closest(".topic-type-delete-btn");
    if (topicTypeDelete) {
      const name = topicTypeDelete.dataset.topicTypeName || "该议题类型";
      if (!window.confirm(`确定删除 ${name} 吗？该类型下的预设议题会一并停用，历史会议记录会保留。`)) return;
      api(`/api/meeting-topic-types/${topicTypeDelete.dataset.topicTypeId}`, { method: "DELETE" })
        .then(refreshAll)
        .then(() => toast("议题类型已删除"))
        .catch((error) => toast(error.message));
      return;
    }
    const meetingEmail = event.target.closest(".meeting-email-btn");
    if (meetingEmail) {
      openMeetingEmailModal(meetingEmail.dataset.meetingId);
      return;
    }
    const meetingSelect = event.target.closest(".meeting-select-btn");
    if (meetingSelect) {
      const meeting = state.meetings.find((item) => Number(item.id) === Number(meetingSelect.dataset.meetingId));
      state.selectedMeetingId = meeting?.id || null;
      if (meeting) state.selectedMeetingDate = meeting.meeting_date;
      renderMeetingCalendar(state.meetings);
      renderMeetingList(state.meetings);
      renderMeetingDetail(meeting);
      return;
    }
    const meetingCell = event.target.closest(".meeting-day");
    if (meetingCell) {
      state.selectedMeetingDate = meetingCell.dataset.date;
      const input = $('input[name="meeting_date"]');
      if (input) input.value = state.selectedMeetingDate;
      const meeting = state.meetings.find((item) => item.meeting_date === state.selectedMeetingDate);
      state.selectedMeetingId = meeting?.id || null;
      renderMeetingCalendar(state.meetings);
      renderMeetingList(state.meetings);
      renderMeetingDetail(meeting || null);
      return;
    }
    const machineDelete = event.target.closest(".machine-delete-btn");
    if (machineDelete) {
      event.stopPropagation();
      const name = machineDelete.dataset.machineName || "该机台";
      if (!window.confirm(`确定删除「${name}」吗？该机台下的排班也会一起删除。`)) return;
      api(`/api/machines/${machineDelete.dataset.machineId}`, { method: "DELETE" })
        .then(refreshAll)
        .then(() => toast("机台已删除"))
        .catch((error) => toast(error.message));
      return;
    }
    const shiftDelete = event.target.closest(".shift-delete-btn");
    if (shiftDelete) {
      event.stopPropagation();
      closeShiftPopover();
      if (!window.confirm("确定删除这条排班吗？")) return;
      api(`/api/shifts/${shiftDelete.dataset.shiftId}`, { method: "DELETE" })
        .then(loadShifts)
        .then(() => toast("排班已删除"))
        .catch((error) => toast(error.message));
      return;
    }
    const shiftCell = event.target.closest(".shift-day");
    if (shiftCell) {
      selectShiftDay(shiftCell);
      return;
    }
  });

  let draggedMemberId = null;
  document.body.addEventListener("dragstart", (event) => {
    const handle = event.target.closest(".member-drag-handle[draggable='true']");
    if (!handle || !isAdminView()) return;
    const card = handle.closest(".member-card");
    draggedMemberId = handle.dataset.memberDragId;
    card?.classList.add("is-dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", `member:${draggedMemberId}`);
  });
  document.body.addEventListener("dragover", (event) => {
    const card = event.target.closest("#memberList .member-card");
    if (!card || !draggedMemberId || card.dataset.memberId === draggedMemberId) return;
    event.preventDefault();
    const placeAfter = event.clientY > card.getBoundingClientRect().top + card.getBoundingClientRect().height / 2;
    $$("#memberList .member-card.is-drop-before, #memberList .member-card.is-drop-after").forEach((entry) => {
      entry.classList.remove("is-drop-before", "is-drop-after");
    });
    card.classList.add(placeAfter ? "is-drop-after" : "is-drop-before");
    event.dataTransfer.dropEffect = "move";
  });
  document.body.addEventListener("drop", (event) => {
    const card = event.target.closest("#memberList .member-card");
    if (!card || !draggedMemberId || card.dataset.memberId === draggedMemberId) return;
    event.preventDefault();
    const placeAfter = card.classList.contains("is-drop-after");
    reorderMemberCards(draggedMemberId, card.dataset.memberId, placeAfter).catch((error) => toast(error.message));
  });
  document.body.addEventListener("dragend", () => {
    draggedMemberId = null;
    $$("#memberList .member-card.is-dragging, #memberList .member-card.is-drop-before, #memberList .member-card.is-drop-after").forEach((entry) => {
      entry.classList.remove("is-dragging", "is-drop-before", "is-drop-after");
    });
  });

  let draggedMorningUserId = null;
  document.body.addEventListener("dragstart", (event) => {
    const item = event.target.closest(".morning-navigator-item[draggable='true']");
    if (!item || !isAdminView()) return;
    draggedMorningUserId = item.dataset.morningNavUserId;
    item.classList.add("is-dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", `morning:${draggedMorningUserId}`);
  });
  document.body.addEventListener("dragover", (event) => {
    const item = event.target.closest(".morning-navigator-item[draggable='true']");
    if (!item || !draggedMorningUserId || item.dataset.morningNavUserId === draggedMorningUserId) return;
    event.preventDefault();
    $$(".morning-navigator-item.is-drop-target").forEach((entry) => entry.classList.remove("is-drop-target"));
    item.classList.add("is-drop-target");
  });
  document.body.addEventListener("drop", (event) => {
    const target = event.target.closest(".morning-navigator-item[draggable='true']");
    if (!target || !draggedMorningUserId || target.dataset.morningNavUserId === draggedMorningUserId) return;
    event.preventDefault();
    const ids = state.morningUsers.map((user) => Number(user.id));
    const from = ids.indexOf(Number(draggedMorningUserId));
    const to = ids.indexOf(Number(target.dataset.morningNavUserId));
    if (from >= 0 && to >= 0) {
      const [moved] = ids.splice(from, 1);
      ids.splice(to, 0, moved);
      saveMorningOrder(ids).catch((error) => toast(error.message));
    }
  });
  document.body.addEventListener("dragend", () => {
    draggedMorningUserId = null;
    $$(".morning-navigator-item.is-dragging, .morning-navigator-item.is-drop-target").forEach((entry) => {
      entry.classList.remove("is-dragging", "is-drop-target");
    });
  });

  let draggedMeetingItemId = null;
  document.body.addEventListener("dragstart", (event) => {
    const item = event.target.closest(".meeting-agenda-item[draggable='true']");
    if (!item) return;
    draggedMeetingItemId = item.dataset.meetingItemId;
    item.classList.add("is-dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", draggedMeetingItemId);
  });
  document.body.addEventListener("dragover", (event) => {
    const item = event.target.closest(".meeting-agenda-item[draggable='true']");
    if (!item || !draggedMeetingItemId) return;
    event.preventDefault();
    $$(".meeting-agenda-item.is-drop-target").forEach((entry) => entry.classList.remove("is-drop-target"));
    if (item.dataset.meetingItemId !== draggedMeetingItemId) item.classList.add("is-drop-target");
  });
  document.body.addEventListener("drop", (event) => {
    const item = event.target.closest(".meeting-agenda-item[draggable='true']");
    const list = item?.closest("[data-meeting-agenda-list]");
    if (!item || !list || !draggedMeetingItemId) return;
    event.preventDefault();
    reorderMeetingAgenda(list.dataset.meetingAgendaList, draggedMeetingItemId, item.dataset.meetingItemId).catch((error) => toast(error.message));
  });
  document.body.addEventListener("dragend", () => {
    draggedMeetingItemId = null;
    $$(".meeting-agenda-item.is-dragging, .meeting-agenda-item.is-drop-target").forEach((entry) => entry.classList.remove("is-dragging", "is-drop-target"));
  });

  document.body.addEventListener("change", (event) => {
    if (event.target.matches("#ssoModeSelect")) {
      updateSsoModeFields();
      return;
    }
    if (event.target.closest("#settingsForm") && event.target.name?.startsWith("sso_")) {
      updateSsoModeFields();
      const persisted = $("#ssoPersistedState");
      if (persisted) {
        persisted.classList.remove("is-saved");
        persisted.innerHTML = "<strong>有未保存的 SSO 改动</strong><span>诊断只读取数据库中的已保存配置</span>";
      }
      return;
    }
    if (event.target.matches('.participation-toggle input[name="participation"]')) {
      const impact = event.target.closest(".user-type-permission-form")?.querySelector("[data-permission-impact]");
      if (impact) impact.innerHTML = "<strong>参与范围已调整</strong><span>点击“评估影响”查看受影响账号和名单变化</span>";
      return;
    }
    if (event.target.matches("#userBulkSelectAll")) {
      $$(".user-bulk-checkbox:not(:disabled)").forEach((input) => {
        const userId = Number(input.value);
        input.checked = event.target.checked;
        if (event.target.checked) state.selectedUserIds.add(userId);
        else state.selectedUserIds.delete(userId);
      });
      updateUserBulkToolbar();
      return;
    }
    if (event.target.matches(".user-bulk-checkbox")) {
      const userId = Number(event.target.value);
      if (event.target.checked) state.selectedUserIds.add(userId);
      else state.selectedUserIds.delete(userId);
      updateUserBulkToolbar();
      return;
    }
    if (event.target.matches("#userOrgFilter, #userTypeFilter, #userAuthFilter")) {
      state.userFilters = {
        ...state.userFilters,
        org: $("#userOrgFilter")?.value || "",
        type: $("#userTypeFilter")?.value || "",
        auth: $("#userAuthFilter")?.value || "",
      };
      renderUserManagement();
      return;
    }
    if (event.target.matches("#userBulkAction")) {
      updateUserBulkActionOptions();
      return;
    }
    if (event.target.matches("#userBulkTarget")) {
      const execute = $("#userBulkExecuteBtn");
      if (execute) execute.disabled = !event.target.value;
      return;
    }
    if (event.target.matches('#memberEditForm input[name="avatar_file"]')) {
      const file = event.target.files?.[0];
      const member = state.members.find((item) => Number(item.id) === Number($("#memberEditForm")?.dataset.memberId));
      if (!file) {
        setMemberAvatarPreview(member?.avatar_url || "", member?.name || "?");
        return;
      }
      fileToDataUrl(file)
        .then((src) => setMemberAvatarPreview(src, member?.name || "?"))
        .catch((error) => toast(error.message));
    }
    if (event.target.matches('.thank-recipient-picker input[name="receiver_ids"]')) {
      updateThankRecipientPicker(event.target.closest(".thank-recipient-picker"));
      return;
    }
    if (event.target.matches('.attendance-donation input[name="donation_done"]')) {
      const form = event.target.closest(".attendance-row");
      saveAttendanceForm(form).catch((error) => toast(error.message));
      return;
    }
    if (event.target.matches("[data-meeting-topic-select]")) updateOptionSelect(event.target);
    if (event.target.matches("[data-meeting-option-select]")) updateTopicOptionDefaults(event.target);
  });

  document.body.addEventListener("input", (event) => {
    if (event.target.matches("#userSearchInput")) {
      state.userFilters.query = event.target.value || "";
      renderUserManagement();
      return;
    }
    if (!event.target.matches('.attendance-donation input[name="donation_amount"]')) return;
    const form = event.target.closest(".attendance-row");
    const stateEl = form?.querySelector(".attendance-save-state");
    if (stateEl) stateEl.textContent = "待保存";
    clearTimeout(form.__attendanceTimer);
    form.__attendanceTimer = setTimeout(() => {
      saveAttendanceForm(form).catch((error) => toast(error.message));
    }, 650);
  });

  document.body.addEventListener("submit", async (event) => {
    const postForm = event.target.closest(".post-form");
    const avatarForm = event.target.closest(".avatar-form");
    const profileForm = event.target.closest(".profile-edit-form");
    const userEditForm = event.target.closest(".user-edit-form");
    const topicForm = event.target.closest(".topic-item-form");
    const meetingTopicScopeForm = event.target.closest(".meeting-topic-scope-form");
    const minuteForm = event.target.closest(".minute-form");
    const presetForm = event.target.closest(".preset-form");
    const linkQualityForm = event.target.closest(".link-quality-form");
    const linkEditForm = event.target.closest("#linkEditForm");
    const chatReplyForm = event.target.closest(".chat-reply-form");
    const morningItemForm = event.target.closest(".morning-item-form");
    const personalMorningForm = event.target.closest(".personal-morning-form");
    const permissionForm = event.target.closest(".user-type-permission-form");
    const passwordForm = event.target.closest("#passwordForm");
    const scoreEditForm = event.target.closest(".score-edit-form");
    if (!postForm && !avatarForm && !profileForm && !userEditForm && !topicForm && !meetingTopicScopeForm && !minuteForm && !presetForm && !linkQualityForm && !linkEditForm && !chatReplyForm && !morningItemForm && !personalMorningForm && !permissionForm && !passwordForm && !scoreEditForm) return;
    event.preventDefault();
    try {
      if (passwordForm) {
        const data = fullFormData(passwordForm);
        if ((data.new_password || "").length < 6) throw new Error("新密码至少 6 位");
        if (data.new_password !== data.confirm_password) throw new Error("两次输入的新密码不一致");
        await api("/api/me/password", { method: "PATCH", body: JSON.stringify(data) });
        closePasswordModal();
        passwordForm.reset();
        toast("密码已更新");
        return;
      }
      if (permissionForm) {
        const permissions = permissionFormPermissions(permissionForm);
        const participation = permissionFormParticipation(permissionForm);
        await assessPermissionImpact(permissionForm);
        const data = await api(`/api/user-types/${permissionForm.dataset.typeKey}/permissions`, {
          method: "PATCH",
          body: JSON.stringify({
            permissions,
            participation,
            name: permissionForm.elements.name?.value || undefined,
            description: permissionForm.elements.description?.value || "",
            expected_version: Number(permissionForm.elements.expected_version?.value || 1),
          }),
        });
        state.userTypes = data.types || state.userTypes;
        state.moduleCatalog = data.modules || state.moduleCatalog;
        if (data.permissions) state.permissions = data.permissions;
        closeUserTypePermissionModal();
        state.thankUsers = [];
        await loadUsers();
        applyAuthView();
        toast(permissionForm.dataset.typeKey === "guest" ? "访客访问范围已保存" : "用户类型与权限已保存");
        return;
      }
      if (linkEditForm) {
        await submitLinkEditForm(linkEditForm);
        toast("链接已更新");
        return;
      }
      if (scoreEditForm) {
        await api(`/api/scores/${scoreEditForm.dataset.scoreId}`, { method: "PATCH", body: JSON.stringify(fullFormData(scoreEditForm)) });
        await loadRulesAndScores();
        toast("积分明细已更新");
        return;
      }
      if (morningItemForm) {
        if (state.morningReadOnly) {
          toast("历史日期只读，不能修改");
          return;
        }
        const data = await api(`/api/morning-items/${morningItemForm.dataset.itemId}`, {
          method: "PATCH",
          body: JSON.stringify(fullFormData(morningItemForm)),
        });
        state.morningItems = data.items || state.morningItems;
        state.morningUsers = data.users || state.morningUsers;
        state.morningVersionToken = data.version_token || state.morningVersionToken;
        state.morningUpdatePending = false;
        renderMorning();
        toast("早例会事项已保存");
        return;
      }
      if (personalMorningForm) {
        await api(`/api/morning-items/${personalMorningForm.dataset.itemId}`, {
          method: "PATCH",
          body: JSON.stringify(fullFormData(personalMorningForm)),
        });
        await loadDashboard();
        toast("事项进展已同步");
        return;
      }
      if (chatReplyForm) {
        const data = await api(`/api/team-posts/${chatReplyForm.dataset.postId}/replies`, { method: "POST", body: JSON.stringify(formData(chatReplyForm)) });
        renderTeamChat(data.posts, true);
        toast("已回复");
        return;
      }
      if (userEditForm) {
        await submitUserEditForm(userEditForm);
        closeUserAccountModal();
        await refreshAll();
        toast("用户已更新");
        return;
      }
      if (postForm) {
        await api(`/api/members/${postForm.dataset.memberId}/posts`, { method: "POST", body: JSON.stringify(formData(postForm)) });
      }
      if (avatarForm) {
        await submitAvatarForm(avatarForm);
      }
      if (profileForm) {
        await submitProfileForm(profileForm);
        closeMemberEditModal();
      }
      if (topicForm) {
        await api(`/api/meetings/${topicForm.dataset.meetingId}/items`, { method: "POST", body: JSON.stringify(formData(topicForm)) });
      }
      if (meetingTopicScopeForm) {
        const topicTypeIds = new FormData(meetingTopicScopeForm).getAll("topic_type_ids");
        await api(`/api/meetings/${meetingTopicScopeForm.dataset.meetingId}/topics`, {
          method: "PATCH",
          body: JSON.stringify({ topic_type_ids: topicTypeIds }),
        });
      }
      if (minuteForm) {
        await api(`/api/meeting-items/${minuteForm.dataset.itemId}`, { method: "PATCH", body: JSON.stringify(fullFormData(minuteForm)) });
        closeMeetingMinuteModal();
      }
      if (presetForm) {
        await api(`/api/meeting-topic-options/${presetForm.dataset.optionId}`, { method: "PATCH", body: JSON.stringify(fullFormData(presetForm)) });
      }
      if (linkQualityForm) {
        await api(`/api/links/${linkQualityForm.dataset.linkId}`, { method: "PATCH", body: JSON.stringify(fullFormData(linkQualityForm)) });
      }
      event.target.reset();
      setDefaultDates();
      await refreshAll();
      toast("已更新");
    } catch (error) {
      toast(error.message);
      if (error.status === 409) refreshPageData(state.currentPage).catch(() => {});
    }
  });
}

async function boot() {
  applyUiTheme();
  setDefaultDates();
  bindEvents();
  try {
    const data = await api("/api/me");
    state.user = data.user;
    state.permissions = data.permissions;
    state.publicSettings = data.settings || {};
    applyOrganizationData(data.organization);
    applyBranding();
    applyAuthView();
    const callbackState = handleSsoCallbackNotice();
    if (maybeStartSsoAutoLogin(callbackState)) return;
    switchPage(pageFromLocation() || "members");
    await refreshAll();
  } catch {
    state.user = null;
    state.permissions = {};
    state.publicSettings = {};
    applyBranding();
    state.showLogin = false;
    applyAuthView();
    const callbackState = handleSsoCallbackNotice();
    if (maybeStartSsoAutoLogin(callbackState)) return;
    await refreshAll();
  }
}

async function startDevelopmentHotReload() {
  let baselineRelease = null;
  try {
    const health = await api("/api/health");
    if (health.environment !== "development") return;
    baselineRelease = health.release;
  } catch {
    return;
  }
  window.setInterval(async () => {
    try {
      const response = await fetch(`/api/health?reload=${Date.now()}`, {
        cache: "no-store",
        credentials: "same-origin",
      });
      if (!response.ok) return;
      const health = await response.json();
      if (health.environment === "development" && health.release && health.release !== baselineRelease) {
        window.location.reload();
      }
    } catch {
      // The development server is briefly unavailable while the watcher restarts it.
    }
  }, 1200);
}

boot().finally(() => {
  startDevelopmentHotReload();
  startMorningPolling();
});
