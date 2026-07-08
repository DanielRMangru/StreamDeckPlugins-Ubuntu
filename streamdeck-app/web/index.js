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
    
    // Application state
    let availablePlugins = [];
    let currentConfig = {};
    let currentDragItem = null;
    let pendingAssignment = null; // { type, index, plugin }



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
        // Reset all key dropzones
        document.querySelectorAll(".key-dropzone").forEach(zone => {
            const index = zone.dataset.index;
            const content = zone.querySelector(".plugin-content");
            const keyConfig = currentConfig.keys[index];

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
            const dialConfig = currentConfig.dials[index];

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
                const configGroup = type === "key" ? currentConfig.keys : currentConfig.dials;
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

    // Search filter logic
    pluginSearch.addEventListener("input", (e) => {
        const query = e.target.value.toLowerCase();
        const filtered = availablePlugins.filter(p => 
            p.name.toLowerCase().includes(query) || 
            p.description.toLowerCase().includes(query)
        );
        renderPlugins(filtered);
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
