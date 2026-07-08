document.addEventListener("DOMContentLoaded", () => {
    // API base URL
    const API_BASE = "/api";
    
    // UI elements
    const statusIndicator = document.querySelector(".status-indicator");
    const statusText = document.querySelector(".status-text");
    const pluginsList = document.getElementById("plugins-list");
    const pluginSearch = document.getElementById("plugin-search");
    const settingsModal = document.getElementById("settings-modal");
    const closeSettingsBtn = document.getElementById("close-settings");
    const settingsForm = document.getElementById("settings-form");
    const dynamicFields = document.getElementById("dynamic-settings-fields");
    const settingsPluginName = document.getElementById("settings-plugin-name");
    const pageTabsContainer = document.getElementById("page-tabs-container");
    const addPageBtn = document.getElementById("add-page-btn");
    
    // Style settings elements
    const stylesMenuBtn = document.getElementById("styles-menu-btn");
    const stylesContentPanel = document.getElementById("styles-content-panel");
    const styleKeyBg = document.getElementById("style-key-bg");
    const styleKeyFont = document.getElementById("style-key-font");
    const styleKeySize = document.getElementById("style-key-size");
    const styleKeyPos = document.getElementById("style-key-pos");
    const styleDialBg = document.getElementById("style-dial-bg");
    const styleDialFont = document.getElementById("style-dial-font");
    const styleDialSize = document.getElementById("style-dial-size");
    const styleDialPos = document.getElementById("style-dial-pos");
    
    // Application state
    let availablePlugins = [];
    let currentConfig = {};
    let currentDragItem = null;
    let pendingAssignment = null; // { type, index, plugin }
    let currentTypeFilter = "all";
    let currentSearchQuery = "";



    // -----------------------------------------------------------------------
    // API Fetchers
    // -----------------------------------------------------------------------
    
    async function checkStatus() {
        try {
            const res = await fetch(`${API_BASE}/status`);
            const data = await res.json();
            
            if (data.status === "Connected") {
                statusIndicator.className = "status-indicator connect";
                statusText.textContent = `${data.device} Connected (${data.serial})`;
            } else {
                statusIndicator.className = "status-indicator disconnect";
                statusText.textContent = "No Stream Deck found";
            }

            // Sync page changes triggered by hardware swipes
            if (data.active_page_index !== undefined && data.active_page_index !== currentConfig.active_page_index) {
                await fetchConfig();
            }
        } catch (e) {
            statusIndicator.className = "status-indicator disconnect";
            statusText.textContent = "Offline (Server Disconnected)";
        }
    }
    
    async function fetchPlugins() {
        try {
            const res = await fetch(`${API_BASE}/plugins`);
            availablePlugins = await res.json();
            renderPlugins(availablePlugins);
        } catch (e) {
            pluginsList.innerHTML = `<div class="loading-spinner">Error loading plugins</div>`;
        }
    }
    
    async function fetchConfig() {
        try {
            const res = await fetch(`${API_BASE}/config`);
            currentConfig = await res.json();
            renderAssignments();
            renderPageTabs();
            initStyleInputs();
        } catch (e) {
            console.error("Error fetching config", e);
        }
    }

    // -----------------------------------------------------------------------
    // UI Renderers
    // -----------------------------------------------------------------------

    function renderPlugins(plugins) {
        pluginsList.innerHTML = "";
        
        if (plugins.length === 0) {
            pluginsList.innerHTML = `<div class="loading-spinner">No plugins found</div>`;
            return;
        }

        plugins.forEach(plugin => {
            const card = document.createElement("div");
            card.className = "plugin-card";
            card.draggable = true;
            card.dataset.class = plugin.class_name;
            card.dataset.target = plugin.target;

            card.innerHTML = `
                <span class="badge ${plugin.target}">${plugin.target.toUpperCase()}</span>
                <h4>${plugin.name}</h4>
                <p>${plugin.description}</p>
            `;

            // Drag Start
            card.addEventListener("dragstart", (e) => {
                currentDragItem = {
                    class_name: plugin.class_name,
                    target: plugin.target,
                    name: plugin.name
                };
                e.dataTransfer.setData("text/plain", plugin.class_name);
                card.style.opacity = "0.5";
            });

            // Drag End
            card.addEventListener("dragend", () => {
                currentDragItem = null;
                card.style.opacity = "1";
            });

            pluginsList.appendChild(card);
        });
    }

    function renderAssignments() {
        const pages = currentConfig.pages || [];
        const activeIdx = currentConfig.active_page_index || 0;
        const activePage = pages[activeIdx] || { keys: {}, dials: {} };

        // Reset all key dropzones
        document.querySelectorAll(".key-dropzone").forEach(zone => {
            const index = zone.dataset.index;
            const content = zone.querySelector(".plugin-content");
            const keyConfig = activePage.keys[index];

            if (keyConfig) {
                const pluginMeta = availablePlugins.find(p => p.class_name === keyConfig.plugin);
                const dispName = pluginMeta ? pluginMeta.name : keyConfig.plugin;
                const subtitle = keyConfig.settings.label || "";
                
                zone.classList.add("assigned");
                content.innerHTML = `
                    <div class="assigned-plugin">
                        <button class="remove-btn" data-type="key" data-index="${index}">&times;</button>
                        <span class="name">${dispName}</span>
                        ${subtitle ? `<span class="desc">${subtitle}</span>` : ""}
                    </div>
                `;
            } else {
                zone.classList.remove("assigned");
                content.innerHTML = `<div class="empty-placeholder">Empty</div>`;
            }
        });

        // Reset all LCD strip segments
        document.querySelectorAll(".lcd-segment").forEach(zone => {
            const index = zone.dataset.index;
            const content = zone.querySelector(".plugin-content");
            const dialConfig = activePage.dials[index];

            if (dialConfig) {
                const pluginMeta = availablePlugins.find(p => p.class_name === dialConfig.plugin);
                const dispName = pluginMeta ? pluginMeta.name : dialConfig.plugin;

                zone.classList.add("assigned");
                content.innerHTML = `
                    <div class="assigned-plugin">
                        <button class="remove-btn" data-type="dial" data-index="${index}">&times;</button>
                        <span class="name">${dispName}</span>
                    </div>
                `;
            } else {
                zone.classList.remove("assigned");
                content.innerHTML = `<div class="empty-placeholder">Empty Zone</div>`;
            }
        });

        // Add event listeners to remove buttons
        document.querySelectorAll(".remove-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const type = btn.dataset.type;
                const index = parseInt(btn.dataset.index);
                removeAssignment(type, index);
            });
        });
        
        // Always apply global styling settings on assignments updates
        applyGlobalStyles();
    }

    // -----------------------------------------------------------------------
    // Drag and Drop Logic
    // -----------------------------------------------------------------------

    function setupDragAndDrop() {
        const dropzones = document.querySelectorAll(".key-dropzone, .lcd-segment");

        dropzones.forEach(zone => {
            // Drag Over
            zone.addEventListener("dragover", (e) => {
                if (!currentDragItem) return;
                
                const zoneType = zone.dataset.type; // "key" or "dial" (dial corresponds to lcd segment)
                if (currentDragItem.target === zoneType || currentDragItem.target === "both") {
                    e.preventDefault();
                    zone.classList.add("dragover");
                }
            });

            // Drag Leave
            zone.addEventListener("dragleave", () => {
                zone.classList.remove("dragover");
            });

            // Drop
            zone.addEventListener("drop", (e) => {
                e.preventDefault();
                zone.classList.remove("dragover");
                
                if (!currentDragItem) return;
                
                const index = parseInt(zone.dataset.index);
                const type = zone.dataset.type;
                
                handleDrop(type, index, currentDragItem.class_name, currentDragItem.name);
            });

            // Click zone to edit settings if assigned
            zone.addEventListener("click", () => {
                const index = zone.dataset.index;
                const type = zone.dataset.type;
                const pages = currentConfig.pages || [];
                const activeIdx = currentConfig.active_page_index || 0;
                const activePage = pages[activeIdx] || { keys: {}, dials: {} };
                const configGroup = type === "key" ? activePage.keys : activePage.dials;
                const assignment = configGroup[index];

                if (assignment) {
                    const pluginMeta = availablePlugins.find(p => p.class_name === assignment.plugin);
                    const name = pluginMeta ? pluginMeta.name : assignment.plugin;
                    openSettings(type, parseInt(index), assignment.plugin, name, assignment.settings);
                }
            });
        });
    }

    function handleDrop(type, index, pluginClass, pluginName) {
        // Check if settings are required
        const pluginMeta = availablePlugins.find(p => p.class_name === pluginClass);
        const schema = pluginMeta && pluginMeta.settings_schema ? pluginMeta.settings_schema : [];
        
        if (schema.length > 0) {
            // Open modal to configure settings
            openSettings(type, index, pluginClass, pluginName);
        } else {
            // Directly assign without modal
            assignPlugin(type, index, pluginClass, {});
        }
    }

    function openSettings(type, index, pluginClass, pluginName, currentSettings = null) {
        pendingAssignment = { type, index, plugin: pluginClass };
        settingsPluginName.textContent = `Configure ${pluginName}`;
        
        // Build settings fields dynamically
        const pluginMeta = availablePlugins.find(p => p.class_name === pluginClass);
        const schema = pluginMeta && pluginMeta.settings_schema ? pluginMeta.settings_schema : [];
        dynamicFields.innerHTML = "";
        
        if (schema.length === 0) {
            dynamicFields.innerHTML = "<p>No custom configuration required for this plugin.</p>";
        } else {
            schema.forEach(field => {
                const val = currentSettings ? currentSettings[field.name] : field.default;
                
                const group = document.createElement("div");
                group.className = "form-group";
                group.innerHTML = `
                    <label for="field-${field.name}">${field.label}</label>
                    <input type="${field.type}" id="field-${field.name}" name="${field.name}" value="${val}" required>
                `;
                dynamicFields.appendChild(group);
            });
        }
        
        settingsModal.classList.add("open");
    }

    function closeSettings() {
        settingsModal.classList.remove("open");
        pendingAssignment = null;
    }

    // -----------------------------------------------------------------------
    // API Call Operations
    // -----------------------------------------------------------------------

    async function assignPlugin(type, index, plugin, settings) {
        try {
            const res = await fetch(`${API_BASE}/assign`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ type, index, plugin, settings })
            });
            const data = await res.json();
            currentConfig = data.config;
            renderAssignments();
            renderPageTabs();
        } catch (e) {
            console.error("Failed to assign plugin", e);
        }
    }

    async function removeAssignment(type, index) {
        try {
            const res = await fetch(`${API_BASE}/remove`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ type, index })
            });
            const data = await res.json();
            currentConfig = data.config;
            renderAssignments();
            renderPageTabs();
        } catch (e) {
            console.error("Failed to remove assignment", e);
        }
    }

    // -----------------------------------------------------------------------
    // Event Listeners
    // -----------------------------------------------------------------------

    closeSettingsBtn.addEventListener("click", closeSettings);
    
    // Close modal clicking outside the card panel
    settingsModal.addEventListener("click", (e) => {
        if (e.target === settingsModal) {
            closeSettings();
        }
    });

    settingsForm.addEventListener("submit", (e) => {
        e.preventDefault();
        if (!pendingAssignment) return;
        
        const formData = new FormData(settingsForm);
        const settings = {};
        formData.forEach((value, key) => {
            settings[key] = value;
        });

        assignPlugin(
            pendingAssignment.type,
            pendingAssignment.index,
            pendingAssignment.plugin,
            settings
        );
        
        closeSettings();
    });

    // Combined filtering logic
    function applyFilters() {
        const filtered = availablePlugins.filter(plugin => {
            // Search query match
            const matchesSearch = plugin.name.toLowerCase().includes(currentSearchQuery) || 
                                  plugin.description.toLowerCase().includes(currentSearchQuery);
            
            // Type filter match
            let matchesType = true;
            if (currentTypeFilter === "key") {
                // Show plugins that can be assigned to buttons (key or both)
                matchesType = (plugin.target === "key" || plugin.target === "both");
            } else if (currentTypeFilter === "dial") {
                // Show plugins that can be assigned to dials (dial or both)
                matchesType = (plugin.target === "dial" || plugin.target === "both");
            } else if (currentTypeFilter === "both") {
                // Show plugins that specifically target both
                matchesType = (plugin.target === "both");
            }
            
            return matchesSearch && matchesType;
        });
        
        renderPlugins(filtered);
    }

    // Search filter logic
    pluginSearch.addEventListener("input", (e) => {
        currentSearchQuery = e.target.value.toLowerCase();
        applyFilters();
    });

    // Filter tabs logic
    const filterTabs = document.querySelectorAll(".filter-tab");
    filterTabs.forEach(tab => {
        tab.addEventListener("click", () => {
            filterTabs.forEach(t => t.classList.remove("active"));
            tab.classList.add("active");
            currentTypeFilter = tab.dataset.filter;
            applyFilters();
        });
    });

    // Page Management Handlers
    function renderPageTabs() {
        if (!pageTabsContainer) return;
        pageTabsContainer.innerHTML = "";
        
        const pages = currentConfig.pages || [];
        const activeIdx = currentConfig.active_page_index || 0;
        
        pages.forEach((page, idx) => {
            const tab = document.createElement("button");
            tab.className = `page-tab ${idx === activeIdx ? 'active' : ''}`;
            tab.innerHTML = `<span>Page ${idx + 1}</span>`;
            
            // Delete button if there is more than 1 page
            if (pages.length > 1) {
                const delBtn = document.createElement("span");
                delBtn.className = "delete-page-btn";
                delBtn.innerHTML = "&times;";
                delBtn.title = "Delete Page";
                delBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    deletePage(idx);
                });
                tab.appendChild(delBtn);
            }
            
            tab.addEventListener("click", () => {
                switchPage(idx);
            });
            
            pageTabsContainer.appendChild(tab);
        });
    }

    async function switchPage(index) {
        try {
            const res = await fetch(`${API_BASE}/pages/switch`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ index })
            });
            const data = await res.json();
            currentConfig = data.config;
            renderAssignments();
            renderPageTabs();
        } catch (e) {
            console.error("Failed to switch page", e);
        }
    }

    async function addPage() {
        try {
            const res = await fetch(`${API_BASE}/pages/add`, {
                method: "POST"
            });
            const data = await res.json();
            currentConfig = data.config;
            renderAssignments();
            renderPageTabs();
        } catch (e) {
            console.error("Failed to add page", e);
        }
    }

    async function deletePage(index) {
        if (!confirm(`Are you sure you want to delete Page ${index + 1}? All plugin assignments on this page will be lost.`)) {
            return;
        }
        try {
            const res = await fetch(`${API_BASE}/pages/delete`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ index })
            });
            const data = await res.json();
            currentConfig = data.config;
            renderAssignments();
            renderPageTabs();
        } catch (e) {
            console.error("Failed to delete page", e);
        }
    }

    if (addPageBtn) {
        addPageBtn.addEventListener("click", addPage);
    }

    // Style settings layout helper functions
    function initStyleInputs() {
        const styles = currentConfig.global_styles;
        if (!styles) return;

        if (styleKeyBg) styleKeyBg.value = styles.key_bg_color;
        if (styleKeyFont) styleKeyFont.value = styles.key_font_family;
        if (styleKeySize) styleKeySize.value = styles.key_font_size;
        if (styleKeyPos) styleKeyPos.value = styles.key_label_position;
        if (styleDialBg) styleDialBg.value = styles.dial_bg_color;
        if (styleDialFont) styleDialFont.value = styles.dial_font_family;
        if (styleDialSize) styleDialSize.value = styles.dial_font_size;
        if (styleDialPos) styleDialPos.value = styles.dial_label_position;

        applyGlobalStyles();
    }

    function applyGlobalStyles() {
        const keyBg = styleKeyBg ? styleKeyBg.value : "#0f172a";
        const keyFont = styleKeyFont ? styleKeyFont.value : "Outfit";
        const keySize = styleKeySize ? styleKeySize.value : "12";
        const keyPos = styleKeyPos ? styleKeyPos.value : "top";

        const dialBg = styleDialBg ? styleDialBg.value : "#0f172a";
        const dialFont = styleDialFont ? styleDialFont.value : "Outfit";
        const dialSize = styleDialSize ? styleDialSize.value : "13";
        const dialPos = styleDialPos ? styleDialPos.value : "left";

        // Style all mockup keys
        document.querySelectorAll(".key-dropzone").forEach(zone => {
            zone.style.backgroundColor = keyBg;
            zone.style.fontFamily = `'${keyFont}', sans-serif`;
            zone.style.fontSize = `${keySize}px`;

            const label = zone.querySelector(".index-label");
            if (label) {
                label.style.top = "auto";
                label.style.bottom = "auto";
                label.style.transform = "none";
                
                if (keyPos === "top") {
                    label.style.top = "8px";
                } else if (keyPos === "bottom") {
                    label.style.bottom = "8px";
                } else if (keyPos === "middle") {
                    label.style.top = "50%";
                    label.style.transform = "translateY(-50%)";
                }
            }

            const content = zone.querySelector(".plugin-content");
            if (content) {
                content.style.height = "100%";
                content.style.display = "flex";
                content.style.flexDirection = "column";
                if (keyPos === "top") {
                    content.style.justifyContent = "flex-end";
                } else if (keyPos === "bottom") {
                    content.style.justifyContent = "flex-start";
                } else {
                    content.style.justifyContent = "center";
                }
            }
        });

        // Style all mockup LCD dial segments
        document.querySelectorAll(".lcd-segment").forEach(zone => {
            zone.style.backgroundColor = dialBg;
            zone.style.fontFamily = `'${dialFont}', sans-serif`;
            zone.style.fontSize = `${dialSize}px`;

            let alignment = "flex-start";
            if (dialPos === "center") alignment = "center";
            else if (dialPos === "right") alignment = "flex-end";

            zone.style.alignItems = alignment;

            const label = zone.querySelector(".segment-label");
            if (label) {
                label.style.left = "auto";
                label.style.right = "auto";
                label.style.transform = "none";
                
                if (dialPos === "left") {
                    label.style.left = "8px";
                } else if (dialPos === "right") {
                    label.style.right = "8px";
                } else if (dialPos === "center") {
                    label.style.left = "50%";
                    label.style.transform = "translateX(-50%)";
                }
            }
            
            const content = zone.querySelector(".plugin-content");
            if (content) {
                content.style.textAlign = dialPos;
            }
        });
    }

    async function saveStyles() {
        const styles = {
            key_bg_color: styleKeyBg.value,
            key_font_family: styleKeyFont.value,
            key_font_size: parseInt(styleKeySize.value) || 12,
            key_label_position: styleKeyPos.value,
            dial_bg_color: styleDialBg.value,
            dial_font_family: styleDialFont.value,
            dial_font_size: parseInt(styleDialSize.value) || 13,
            dial_label_position: styleDialPos.value
        };

        try {
            const res = await fetch(`${API_BASE}/styles`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(styles)
            });
            const data = await res.json();
            currentConfig = data.config;
        } catch (e) {
            console.error("Failed to save styles", e);
        }
    }

    // Set up style form listeners
    const styleInputs = [
        styleKeyBg, styleKeyFont, styleKeySize, styleKeyPos,
        styleDialBg, styleDialFont, styleDialSize, styleDialPos
    ];
    styleInputs.forEach(input => {
        if (input) {
            input.addEventListener("input", applyGlobalStyles);
            input.addEventListener("change", saveStyles);
        }
    });

    // Global Styles dropdown toggler
    if (stylesMenuBtn) {
        stylesMenuBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            const isCollapsed = stylesContentPanel.classList.toggle("collapsed");
            stylesMenuBtn.classList.toggle("active", !isCollapsed);
        });
    }

    // Close global styles dropdown when clicking outside
    document.addEventListener("click", (e) => {
        if (stylesContentPanel && !stylesContentPanel.classList.contains("collapsed")) {
            if (!stylesContentPanel.contains(e.target) && e.target !== stylesMenuBtn && !stylesMenuBtn.contains(e.target)) {
                stylesContentPanel.classList.add("collapsed");
                stylesMenuBtn.classList.remove("active");
            }
        }
    });

    // -----------------------------------------------------------------------
    // App Initialization
    // -----------------------------------------------------------------------
    
    async function init() {
        await checkStatus();
        await fetchPlugins();
        await fetchConfig();
        setupDragAndDrop();
        
        // Keep checking device status every 3 seconds
        setInterval(checkStatus, 3000);
    }
    
    init();
});
