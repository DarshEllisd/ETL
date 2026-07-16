document.addEventListener("DOMContentLoaded", () => {
    // Nav Tab elements
    const navItems = document.querySelectorAll(".nav-item");
    const tabPanels = document.querySelectorAll(".tab-panel");
    const pageTitle = document.getElementById("page-title");
    const pageDesc = document.getElementById("page-desc");

    // Pipeline elements
    const runBtn = document.getElementById("run-pipeline-btn");
    const cleanSlateBtn = document.getElementById("clean-slate-btn");
    const consoleOutput = document.getElementById("console-output");
    const clearConsoleBtn = document.getElementById("clear-console-btn");
    
    function showConsole(msg) {
        if (consoleOutput) {
            consoleOutput.innerText += `\n${msg}`;
            consoleOutput.scrollTop = consoleOutput.scrollHeight;
        }
    }
    
    // Auditor elements
    const audVersionSelect = document.getElementById("auditor-version-select");
    const auditorMetricsGrid = document.getElementById("auditor-metrics-grid");
    const auditorVizContainer = document.getElementById("auditor-viz-container");
    const auditorPreviewContainer = document.getElementById("auditor-preview-container");
    const audConvCount = document.getElementById("aud-conv-count");
    const audMsgCount = document.getElementById("aud-msg-count");
    const audAvgLen = document.getElementById("aud-avg-len");
    const piiEmailsLbl = document.getElementById("pii-emails-lbl");
    const piiPhonesLbl = document.getElementById("pii-phones-lbl");
    const piiPasswordsLbl = document.getElementById("pii-passwords-lbl");
    const piiAddressesLbl = document.getElementById("pii-addresses-lbl");
    const piiNsfwLbl = document.getElementById("pii-nsfw-lbl");
    const piiPrivateLbl = document.getElementById("pii-private-lbl");
    const chartGmailBar = document.getElementById("chart-gmail-bar");
    const chartWhatsappBar = document.getElementById("chart-whatsapp-bar");
    const lblGmailCount = document.getElementById("lbl-gmail-count");
    const lblWhatsappCount = document.getElementById("lbl-whatsapp-count");
    const previewMessagesList = document.getElementById("preview-messages-list");
    const auditorPendingContainer = document.getElementById("auditor-pending-container");
    const pendingCountLbl = document.getElementById("pending-count-lbl");
    const pendingMessagesList = document.getElementById("pending-messages-list");
    const approveAllBtn = document.getElementById("approve-all-btn");
    const auditorRolesContainer = document.getElementById("auditor-roles-container");
    const rolesListContainer = document.getElementById("roles-list-container");
    const saveRolesBtn = document.getElementById("save-roles-btn");

    // Language Explorer elements
    const auditorExplorerLayout = document.getElementById("auditor-explorer-layout");
    const languagesList = document.getElementById("languages-list");
    const auditorFlaggedContainer = document.getElementById("auditor-flagged-container");
    const flaggedCountLbl = document.getElementById("flagged-count-lbl");
    const flaggedMessagesList = document.getElementById("flagged-messages-list");
    const browserTitleLbl = document.getElementById("browser-title-lbl");

    // Dynamic configuration variables
    let availableVersions = [];
    let activeLanguage = "All";
    let lastFetchedDetails = null;

    // Diff elements
    const diffV1Select = document.getElementById("diff-v1-select");
    const diffV2Select = document.getElementById("diff-v2-select");
    const compareBtn = document.getElementById("compare-btn");
    const diffReportContainer = document.getElementById("diff-report-container");
    const diffMetricsTable = document.getElementById("diff-metrics-table").querySelector("tbody");
    const diffPiiTable = document.getElementById("diff-pii-table").querySelector("tbody");

    // Tab Switching Navigation
    navItems.forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            const tabId = item.getAttribute("data-tab");
            
            navItems.forEach(n => n.classList.remove("active"));
            tabPanels.forEach(p => p.classList.remove("active"));
            
            item.classList.add("active");
            document.getElementById(tabId).classList.add("active");

            // Update header headers
            if (tabId === "pipeline-tab") {
                pageTitle.innerText = "ETL Execution Hub";
                pageDesc.innerText = "Run, trace, and monitor pipeline stages";
            } else if (tabId === "auditor-tab") {
                pageTitle.innerText = "Dataset Auditor";
                pageDesc.innerText = "Evaluate and audit exported LLM training sets";
                loadStatus(); // refresh dropdown versions
            } else if (tabId === "diff-tab") {
                pageTitle.innerText = "Version Comparison";
                pageDesc.innerText = "Audit changes between dataset versions";
                loadStatus(); // refresh dropdown versions
            }
        });
    });

    // Clear log console screen
    clearConsoleBtn.addEventListener("click", () => {
        consoleOutput.innerText = "Console cleared. Click 'Launch ETL Run' to start.";
        resetStepNodes();
    });

    // Load initial system stats
    async function loadStatus() {
        try {
            const res = await fetch(`/api/status?_t=${Date.now()}`);
            const data = await res.json();
            
            // Populate Config Badge and Status details
            const version = data.config.dataset?.version || "1.0.0";
            document.getElementById("config-version-lbl").innerText = `Config version: v${version}`;
            document.getElementById("stat-active-version").innerText = `v${version}`;

            // Set file counters
            document.getElementById("stat-raw-files").innerText = 
                `${data.counts.raw_gmail + data.counts.raw_whatsapp} files (${data.counts.raw_gmail} EML / ${data.counts.raw_whatsapp} TXT)`;
            document.getElementById("stat-norm-files").innerText = 
                `${data.counts.normalized_gmail + data.counts.normalized_whatsapp} files (${data.counts.normalized_gmail} EML / ${data.counts.normalized_whatsapp} TXT)`;

            // Store versions list
            availableVersions = data.versions || [];
            populateVersionSelects();
        } catch (err) {
            console.error("Failed to load status details:", err);
        }
    }

    // Populate drop down versions selectors
    function populateVersionSelects() {
        const prevAudValue = audVersionSelect.value;
        const prevDiffV1 = diffV1Select.value;
        const prevDiffV2 = diffV2Select.value;

        // Clear existing options
        audVersionSelect.innerHTML = "";
        diffV1Select.innerHTML = "";
        diffV2Select.innerHTML = "";

        if (availableVersions.length === 0) {
            const emptyOpt = '<option value="">No versions available</option>';
            audVersionSelect.innerHTML = emptyOpt;
            diffV1Select.innerHTML = emptyOpt;
            diffV2Select.innerHTML = emptyOpt;
            return;
        }

        availableVersions.forEach(v => {
            const opt = `<option value="${v}">${v}</option>`;
            audVersionSelect.innerHTML += opt;
            diffV1Select.innerHTML += opt;
            diffV2Select.innerHTML += opt;
        });

        // Restore values if still available
        if (availableVersions.includes(prevAudValue)) audVersionSelect.value = prevAudValue;
        if (availableVersions.includes(prevDiffV1)) diffV1Select.value = prevDiffV1;
        if (availableVersions.includes(prevDiffV2)) diffV2Select.value = prevDiffV2;
        
        // Auto trigger auditor view
        if (audVersionSelect.value) {
            loadDatasetDetails(audVersionSelect.value);
        }
    }

    // Trigger pipeline run
    runBtn.addEventListener("click", async () => {
        runBtn.disabled = true;
        runBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';
        consoleOutput.innerText = "Starting pipeline run...\n";
        resetStepNodes();

        try {
            const res = await fetch("/api/run", { method: "POST" });
            const data = await res.json();
            
            if (data.error) {
                consoleOutput.innerText += `\nError: ${data.error}`;
                highlightErrorInConsole();
            } else {
                // Stream log logs sequentially
                const lines = data.logs.split("\n");
                consoleOutput.innerText = "";
                
                let delay = 0;
                lines.forEach((line) => {
                    setTimeout(() => {
                        // Apply colorful logging tags
                        let coloredLine = line;
                        if (line.includes("[INFO]")) {
                            coloredLine = line.replace("[INFO]", '<span class="log-info">[INFO]</span>');
                        } else if (line.includes("[WARNING]")) {
                            coloredLine = line.replace("[WARNING]", '<span class="log-warn">[WARNING]</span>');
                        } else if (line.includes("[ERROR]")) {
                            coloredLine = line.replace("[ERROR]", '<span class="log-error">[ERROR]</span>');
                        }
                        
                        consoleOutput.innerHTML += coloredLine + "\n";
                        consoleOutput.scrollTop = consoleOutput.scrollHeight;
                        
                        // Dynamically trace visual steps nodes based on logs content
                        parseLogForStepProgress(line);
                    }, delay);
                    delay += 80; // speed visual run
                });
                
                setTimeout(() => {
                    consoleOutput.innerHTML += '\n<span class="log-success">ETL Pipeline run successfully complete!</span>\n';
                    consoleOutput.scrollTop = consoleOutput.scrollHeight;
                    loadStatus(); // refresh datasets counters / versions
                }, delay + 200);
            }
        } catch (err) {
            consoleOutput.innerText += `\nNetwork failure: ${err}`;
        } finally {
            setTimeout(() => {
                runBtn.disabled = false;
                runBtn.innerHTML = '<i class="fa-solid fa-play"></i> Launch ETL Run';
            }, 1000);
        }
    });

    // Reset step indicator nodes
    function resetStepNodes() {
        const nodes = document.querySelectorAll(".step-node");
        nodes.forEach(n => {
            n.classList.remove("active", "completed");
        });
    }

    // Step parser trace highlighting
    function parseLogForStepProgress(logLine) {
        // Map log patterns to node IDs
        const mappings = [
            { pattern: "Ingesting raw logs...", current: "step-ingest", prevs: [] },
            { pattern: "Normalizing raw data...", current: "step-normalize", prevs: ["step-ingest"] },
            { pattern: "Merging normalized messages...", current: "step-merge", prevs: ["step-ingest", "step-normalize"] },
            { pattern: "Reconstructing threads", current: "step-reconstruct", prevs: ["step-ingest", "step-normalize", "step-merge"] },
            { pattern: "Stripping signatures", current: "step-clean", prevs: ["step-ingest", "step-normalize", "step-merge", "step-reconstruct"] },
            { pattern: "Scrubbing PII", current: "step-anonymize", prevs: ["step-ingest", "step-normalize", "step-merge", "step-reconstruct", "step-clean"] },
            { pattern: "Generating LLM-assisted advanced annotations", current: "step-annotate", prevs: ["step-ingest", "step-normalize", "step-merge", "step-reconstruct", "step-clean", "step-anonymize"] },
            { pattern: "Translating regional languages", current: "step-translate", prevs: ["step-ingest", "step-normalize", "step-merge", "step-reconstruct", "step-clean", "step-anonymize", "step-annotate"] },
            { pattern: "Exporting final instruction datasets", current: "step-export", prevs: ["step-ingest", "step-normalize", "step-merge", "step-reconstruct", "step-clean", "step-anonymize", "step-annotate", "step-translate"] },
            { pattern: "Creating semantic dialogue segments", current: "step-rag", prevs: ["step-ingest", "step-normalize", "step-merge", "step-reconstruct", "step-clean", "step-anonymize", "step-annotate", "step-translate", "step-export"] },
            { pattern: "completed successfully.", current: "", prevs: ["step-ingest", "step-normalize", "step-merge", "step-reconstruct", "step-clean", "step-anonymize", "step-annotate", "step-translate", "step-export", "step-rag"] }
        ];

        mappings.forEach(m => {
            if (logLine.includes(m.pattern)) {
                resetStepNodes();
                m.prevs.forEach(pId => {
                    document.getElementById(pId).classList.add("completed");
                });
                if (m.current) {
                    document.getElementById(m.current).classList.add("active");
                }
            }
        });
    }

    // Auditor selector handler
    audVersionSelect.addEventListener("change", () => {
        if (audVersionSelect.value) {
            loadDatasetDetails(audVersionSelect.value);
        }
    });

    // Load dataset metadata details for Auditor
    async function loadDatasetDetails(version) {
        try {
            const res = await fetch(`/api/dataset-details?version=${version}&_t=${Date.now()}`);
            const data = await res.json();
            
            function appendMessageRow(container, msg) {
                const msgDiv = document.createElement("div");
                msgDiv.className = "preview-msg";
                msgDiv.style.display = "flex";
                msgDiv.style.alignItems = "baseline";
                msgDiv.style.justifyContent = "space-between";
                msgDiv.style.gap = "12px";
                
                const leftSpan = document.createElement("div");
                leftSpan.style.display = "flex";
                leftSpan.style.alignItems = "baseline";
                leftSpan.style.gap = "8px";
                
                const roleSpan = document.createElement("span");
                roleSpan.className = `msg-role ${msg.role}`;
                roleSpan.innerText = `${msg.role}:`;
                
                const textSpan = document.createElement("span");
                textSpan.className = "msg-text";
                textSpan.innerText = msg.content;
                
                leftSpan.appendChild(roleSpan);
                leftSpan.appendChild(textSpan);
                msgDiv.appendChild(leftSpan);
                
                if (msg.detected_languages && msg.detected_languages.length > 0) {
                    const langTag = document.createElement("span");
                    langTag.style.fontSize = "10px";
                    langTag.style.background = "rgba(255, 255, 255, 0.03)";
                    langTag.style.border = "1px solid rgba(255, 255, 255, 0.05)";
                    langTag.style.padding = "1px 6px";
                    langTag.style.borderRadius = "10px";
                    langTag.style.color = "var(--text-secondary)";
                    langTag.style.flexShrink = "0";
                    langTag.innerText = msg.detected_languages.join(", ");
                    msgDiv.appendChild(langTag);
                }
                container.appendChild(msgDiv);
            }
            
            if (data.error) {
                console.error(data.error);
                return;
            }
            
            // Show grids
            auditorMetricsGrid.style.display = "grid";
            auditorVizContainer.style.display = "grid";
            auditorPreviewContainer.style.display = "block";
            auditorPendingContainer.style.display = "block";
            auditorRolesContainer.style.display = "block";
            pendingCountLbl.innerText = data.pending ? data.pending.length : 0;

            // Card details
            audConvCount.innerText = data.metadata.total_conversations || 0;
            audMsgCount.innerText = data.metadata.total_messages || 0;
            
            const avgLen = data.statistics.conversation_length_stats?.average || 0;
            audAvgLen.innerText = `${avgLen.toFixed(1)} turns`;

            // PII
            const pii = data.metadata.anonymization_summary || {};
            piiEmailsLbl.innerText = pii.emails_scrubbed || 0;
            piiPhonesLbl.innerText = pii.phones_scrubbed || 0;
            piiPasswordsLbl.innerText = pii.passwords_scrubbed || 0;
            piiAddressesLbl.innerText = pii.addresses_scrubbed || 0;
            piiNsfwLbl.innerText = pii.nsfw_messages_scrubbed || 0;
            piiPrivateLbl.innerText = pii.private_messages_scrubbed || 0;

            // Chart bar distribution math
            const gmail = data.metadata.source_distribution?.gmail || 0;
            const wa = data.metadata.source_distribution?.whatsapp || 0;
            const total = gmail + wa;
            const gmailPercent = total > 0 ? (gmail / total) * 100 : 50;
            const waPercent = total > 0 ? (wa / total) * 100 : 50;
            
            chartGmailBar.style.width = `${gmailPercent}%`;
            chartWhatsappBar.style.width = `${waPercent}%`;
            lblGmailCount.innerText = gmail;
            lblWhatsappCount.innerText = wa;

            lastFetchedDetails = data;
            
            // Show new explorer layout
            auditorExplorerLayout.style.display = "flex";

            // 1. Render Language Explorer sidebar list
            languagesList.innerHTML = "";
            const langCounts = { "All": data.approved_conversations.length };
            data.all_seen_languages.forEach(l => {
                langCounts[l] = data.approved_conversations.filter(c => c.detected_languages.includes(l)).length;
            });

            // Add 'All' item
            const allLi = document.createElement("li");
            allLi.className = `lang-item ${activeLanguage === "All" ? "active" : ""}`;
            allLi.innerHTML = `<span>All Languages</span> <span class="lang-badge">${langCounts["All"]}</span>`;
            allLi.addEventListener("click", () => {
                activeLanguage = "All";
                renderApprovedBrowser();
                document.querySelectorAll(".lang-item").forEach(li => li.classList.remove("active"));
                allLi.classList.add("active");
            });
            languagesList.appendChild(allLi);

            // Add individual languages
            data.all_seen_languages.forEach(lang => {
                const li = document.createElement("li");
                li.className = `lang-item ${activeLanguage === lang ? "active" : ""}`;
                li.innerHTML = `<span>${lang}</span> <span class="lang-badge">${langCounts[lang]}</span>`;
                li.addEventListener("click", () => {
                    activeLanguage = lang;
                    renderApprovedBrowser();
                    document.querySelectorAll(".lang-item").forEach(item => item.classList.remove("active"));
                    li.classList.add("active");
                });
                languagesList.appendChild(li);
            });

            // Helper to render approved browser grid
            function renderApprovedBrowser() {
                previewMessagesList.innerHTML = "";
                browserTitleLbl.innerText = `Database Explorer: Approved Conversations (${activeLanguage})`;
                
                let filtered = data.approved_conversations || [];
                if (activeLanguage !== "All") {
                    filtered = filtered.filter(c => c.detected_languages.includes(activeLanguage));
                }
                
                if (filtered.length === 0) {
                    previewMessagesList.innerHTML = `<p class="text-secondary" style="padding: 12px;">No conversations found matching language ${activeLanguage}.</p>`;
                    return;
                }
                
                filtered.forEach((row, i) => {
                    const convCard = document.createElement("div");
                    convCard.className = "preview-conv";
                    if (row.flagged) {
                        convCard.style.borderColor = "rgba(239, 68, 68, 0.3)";
                    }
                    
                    const header = document.createElement("div");
                    header.className = "preview-conv-header";
                    
                    const title = document.createElement("div");
                    title.className = "preview-conv-title";
                    title.innerText = `APPROVED RECORD #${i + 1} (${row.conversation_id || "Unknown ID"})`;
                    header.appendChild(title);
                    
                    // Language badge list
                    const langBadge = document.createElement("span");
                    langBadge.style.fontSize = "11px";
                    langBadge.style.background = "rgba(255, 255, 255, 0.05)";
                    langBadge.style.padding = "2px 8px";
                    langBadge.style.borderRadius = "4px";
                    langBadge.style.color = "var(--text-secondary)";
                    langBadge.innerText = `🌐 ${row.detected_languages.join(", ")}`;
                    header.appendChild(langBadge);
                    
                    const excludeBtn = document.createElement("button");
                    excludeBtn.className = "btn-exclude";
                    excludeBtn.innerHTML = '<i class="fa-solid fa-trash"></i> Exclude';
                    excludeBtn.addEventListener("click", () => {
                        excludeConversation(version, row.conversation_id);
                    });
                    header.appendChild(excludeBtn);
                    convCard.appendChild(header);

                    if (row.flagged) {
                        const warnDiv = document.createElement("div");
                        warnDiv.style.background = "rgba(239, 68, 68, 0.1)";
                        warnDiv.style.border = "1px solid rgba(239, 68, 68, 0.2)";
                        warnDiv.style.padding = "6px 12px";
                        warnDiv.style.borderRadius = "4px";
                        warnDiv.style.marginBottom = "12px";
                        warnDiv.style.fontSize = "12px";
                        warnDiv.style.color = "#ef4444";
                        warnDiv.style.display = "flex";
                        warnDiv.style.alignItems = "center";
                        warnDiv.style.gap = "8px";
                        warnDiv.style.flexWrap = "wrap";
                        const warnText = document.createElement("span");
                        warnText.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> <strong>New language detected:</strong> ${row.flagged_languages.join(", ")}.`;
                        warnDiv.appendChild(warnText);
                        row.flagged_languages.forEach(lang => {
                            warnDiv.appendChild(createFlaggedControls(lang, version));
                        });
                        convCard.appendChild(warnDiv);
                    }
                    
                    row.messages.forEach(msg => {
                        appendMessageRow(convCard, msg);
                    });
                    previewMessagesList.appendChild(convCard);
                });
            }
            
            // Initial call to render approved conversations
            renderApprovedBrowser();

            // 2. Render Flagged review inbox
            flaggedMessagesList.innerHTML = "";
            const flaggedConvs = [];
            if (data.pending) {
                data.pending.forEach(c => { if (c.flagged) flaggedConvs.push({ ...c, status: "pending" }); });
            }
            if (data.approved_conversations) {
                data.approved_conversations.forEach(c => { if (c.flagged) flaggedConvs.push({ ...c, status: "approved" }); });
            }
            
            flaggedCountLbl.innerText = flaggedConvs.length;
            if (flaggedConvs.length > 0) {
                auditorFlaggedContainer.style.display = "block";
                flaggedConvs.forEach((row, i) => {
                    const convCard = document.createElement("div");
                    convCard.className = "preview-conv";
                    convCard.style.borderColor = "rgba(239, 68, 68, 0.4)";
                    
                    const header = document.createElement("div");
                    header.className = "preview-conv-header";
                    
                    const title = document.createElement("div");
                    title.className = "preview-conv-title";
                    title.style.color = "#ef4444";
                    title.innerText = `FLAGGED RECORD #${i + 1} (${row.conversation_id || "Unknown ID"}) [${row.status.toUpperCase()}]`;
                    header.appendChild(title);
                    
                    convCard.appendChild(header);

                    const warnDiv = document.createElement("div");
                    warnDiv.style.background = "rgba(239, 68, 68, 0.1)";
                    warnDiv.style.border = "1px solid rgba(239, 68, 68, 0.2)";
                    warnDiv.style.padding = "6px 12px";
                    warnDiv.style.borderRadius = "4px";
                    warnDiv.style.marginBottom = "12px";
                    warnDiv.style.fontSize = "12px";
                    warnDiv.style.color = "#ef4444";
                    warnDiv.style.display = "flex";
                    warnDiv.style.alignItems = "center";
                    warnDiv.style.gap = "8px";
                    warnDiv.style.flexWrap = "wrap";
                    
                    const warnText = document.createElement("span");
                    warnText.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i> <strong>Contains unapproved language(s):</strong> ${row.flagged_languages.join(", ")}.`;
                    warnDiv.appendChild(warnText);
                    
                    row.flagged_languages.forEach(lang => {
                        warnDiv.appendChild(createFlaggedControls(lang, version));
                    });
                    convCard.appendChild(warnDiv);
                    
                    row.messages.forEach(msg => {
                        appendMessageRow(convCard, msg);
                    });
                    flaggedMessagesList.appendChild(convCard);
                });
            } else {
                auditorFlaggedContainer.style.display = "none";
            }

            // 3. Render Pending list (only non-flagged pending, or all pending)
            pendingMessagesList.innerHTML = "";
            if (!data.pending || data.pending.length === 0) {
                pendingMessagesList.innerHTML = '<p class="text-secondary" style="font-size: 13px; padding: 12px;">No pending conversations require review.</p>';
            } else {
                data.pending.forEach((row, i) => {
                    const convCard = document.createElement("div");
                    convCard.className = "preview-conv";
                    convCard.style.borderColor = row.flagged ? "rgba(239, 68, 68, 0.25)" : "rgba(99, 102, 241, 0.15)";
                    
                    const header = document.createElement("div");
                    header.className = "preview-conv-header";
                    
                    const title = document.createElement("div");
                    title.className = "preview-conv-title";
                    title.innerText = `PENDING RECORD #${i + 1} (${row.conversation_id || "Unknown ID"})`;
                    header.appendChild(title);
                    
                    // Language tag
                    const langBadge = document.createElement("span");
                    langBadge.style.fontSize = "10px";
                    langBadge.style.background = "rgba(255, 255, 255, 0.04)";
                    langBadge.style.padding = "1px 6px";
                    langBadge.style.borderRadius = "3px";
                    langBadge.style.color = "var(--text-secondary)";
                    langBadge.innerText = `🌐 ${row.detected_languages.join(", ")}`;
                    header.appendChild(langBadge);

                    const approveBtn = document.createElement("button");
                    approveBtn.className = "btn-approve";
                    approveBtn.innerHTML = '<i class="fa-solid fa-plus"></i> Add to Dataset';
                    approveBtn.addEventListener("click", () => {
                        approveConversation(version, row.conversation_id);
                    });
                    header.appendChild(approveBtn);
                    convCard.appendChild(header);

                    if (row.flagged) {
                        const warnDiv = document.createElement("div");
                        warnDiv.style.background = "rgba(239, 68, 68, 0.08)";
                        warnDiv.style.border = "1px solid rgba(239, 68, 68, 0.15)";
                        warnDiv.style.padding = "4px 8px";
                        warnDiv.style.borderRadius = "4px";
                        warnDiv.style.marginBottom = "8px";
                        warnDiv.style.fontSize = "11px";
                        warnDiv.style.color = "#ef4444";
                        warnDiv.style.display = "flex";
                        warnDiv.style.alignItems = "center";
                        warnDiv.style.gap = "8px";
                        warnDiv.style.flexWrap = "wrap";
                        const warnText = document.createElement("span");
                        warnText.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Requires language approval for: ${row.flagged_languages.join(", ")}.`;
                        warnDiv.appendChild(warnText);
                        row.flagged_languages.forEach(lang => {
                            warnDiv.appendChild(createFlaggedControls(lang, version));
                        });
                        convCard.appendChild(warnDiv);
                    }
                    
                    row.messages.forEach(msg => {
                        appendMessageRow(convCard, msg);
                    });
                    pendingMessagesList.appendChild(convCard);
                });
            }

            // Roles list builder
            rolesListContainer.innerHTML = "";
            if (!data.participants || data.participants.length === 0) {
                rolesListContainer.innerHTML = '<p class="text-secondary" style="font-size: 13px;">No participants found in dataset.</p>';
            } else {
                data.participants.forEach(p => {
                    const row = document.createElement("div");
                    row.style.display = "flex";
                    row.style.justifyContent = "space-between";
                    row.style.alignItems = "center";
                    row.style.padding = "6px 12px";
                    row.style.background = "rgba(255, 255, 255, 0.02)";
                    row.style.borderRadius = "4px";
                    row.style.border = "1px solid rgba(255, 255, 255, 0.05)";
                    
                    const nameSpan = document.createElement("span");
                    nameSpan.style.fontSize = "13px";
                    nameSpan.style.fontWeight = "500";
                    nameSpan.innerText = p;
                    
                    const select = document.createElement("select");
                    select.className = "styled-select";
                    select.style.padding = "2px 8px";
                    select.style.fontSize = "12px";
                    select.style.width = "auto";
                    select.style.margin = "0";
                    select.dataset.name = p;
                    
                    const optUser = document.createElement("option");
                    optUser.value = "user";
                    optUser.innerText = "Customer (User)";
                    
                    const optAgent = document.createElement("option");
                    optAgent.value = "assistant";
                    optAgent.innerText = "Agent (Assistant)";
                    
                    const isAgent = data.agents.some(a => a.toLowerCase().trim() === p.toLowerCase().trim());
                    if (isAgent) {
                        optAgent.selected = true;
                    } else {
                        optUser.selected = true;
                    }
                    
                    select.appendChild(optUser);
                    select.appendChild(optAgent);
                    
                    row.appendChild(nameSpan);
                    row.appendChild(select);
                    rolesListContainer.appendChild(row);
                });
            }

            saveRolesBtn.onclick = async () => {
                const selectedAgents = [];
                rolesListContainer.querySelectorAll("select").forEach(sel => {
                    if (sel.value === "assistant") {
                        selectedAgents.push(sel.dataset.name);
                    }
                });
                
                saveRolesBtn.disabled = true;
                const origHtml = saveRolesBtn.innerHTML;
                saveRolesBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';
                
                try {
                    const res = await fetch("/api/save-roles", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ version, agents: selectedAgents })
                    });
                    const resData = await res.json();
                    if (resData.error) {
                        alert(`Error saving roles: ${resData.error}`);
                    } else {
                        alert("Roles saved successfully! Dataset re-processed.");
                        loadDatasetDetails(version);
                        loadStatus();
                    }
                } catch (err) {
                    alert(`Network error saving roles: ${err}`);
                } finally {
                    saveRolesBtn.disabled = false;
                    saveRolesBtn.innerHTML = origHtml;
                }
            };

        } catch (err) {
            console.error("Failed to load dataset details:", err);
        }
    }

    async function excludeConversation(version, conversationId) {
        if (!conversationId) {
            alert("Cannot exclude: Conversation ID not found.");
            return;
        }
        if (!confirm(`Are you sure you want to persistently exclude conversation ${conversationId}?`)) {
            return;
        }
        
        try {
            const res = await fetch("/api/exclude-conversation", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ version, conversation_id: conversationId })
            });
            const data = await res.json();
            if (data.error) {
                alert(`Error: ${data.error}`);
            } else {
                loadDatasetDetails(version);
                loadStatus();
            }
        } catch (err) {
            alert(`Failed to exclude conversation: ${err}`);
        }
    }

    async function approveConversation(version, conversationId) {
        if (!conversationId) {
            alert("Cannot approve: Conversation ID not found.");
            return;
        }
        if (!confirm(`Are you sure you want to approve conversation ${conversationId} and add it to the dataset?`)) {
            return;
        }
        
        try {
            const res = await fetch("/api/approve-conversation", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ version, conversation_id: conversationId })
            });
            const data = await res.json();
            if (data.error) {
                alert(`Error: ${data.error}`);
            } else {
                loadDatasetDetails(version);
                loadStatus();
            }
        } catch (err) {
            alert(`Failed to approve conversation: ${err}`);
        }
    }

    // Comparison diff handler
    compareBtn.addEventListener("click", async () => {
        const v1 = diffV1Select.value;
        const v2 = diffV2Select.value;
        
        if (!v1 || !v2) {
            alert("Please select two versions to compare.");
            return;
        }

        try {
            const res = await fetch("/api/diff", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ v1, v2 })
            });
            const data = await res.json();
            
            if (data.error) {
                alert(`Comparison Error: ${data.error}`);
                return;
            }
            
            // Show table content
            diffReportContainer.style.display = "block";
            document.getElementById("th-v1").innerText = data.version1;
            document.getElementById("th-v2").innerText = data.version2;
            document.getElementById("th-pii-v1").innerText = data.version1;
            document.getElementById("th-pii-v2").innerText = data.version2;

            // Render Metrics Rows
            diffMetricsTable.innerHTML = "";
            renderDiffRow(diffMetricsTable, "Total Conversations", data.metrics.total_conversations);
            renderDiffRow(diffMetricsTable, "Total Messages", data.metrics.total_messages);
            renderDiffRow(diffMetricsTable, "Unique Vocabulary Size", data.metrics.vocabulary_size);
            renderDiffRow(diffMetricsTable, "Estimated Total Tokens", data.metrics.estimated_total_tokens);

            // Render PII Rows
            diffPiiTable.innerHTML = "";
            renderDiffRow(diffPiiTable, "Emails Redacted", data.anonymization.emails_scrubbed);
            renderDiffRow(diffPiiTable, "Phones Redacted", data.anonymization.phones_scrubbed);
            renderDiffRow(diffPiiTable, "Passwords Redacted", data.anonymization.passwords_scrubbed);
            renderDiffRow(diffPiiTable, "Addresses Redacted", data.anonymization.addresses_scrubbed);

        } catch (err) {
            alert(`Comparison failed: ${err}`);
        }
    });

    // Helper row builder inside tables comparison
    function renderDiffRow(tableBody, label, metricsObj) {
        const tr = document.createElement("tr");
        
        const tdLabel = document.createElement("td");
        tdLabel.innerText = label;
        tr.appendChild(tdLabel);
        
        const tdV1 = document.createElement("td");
        tdV1.innerText = metricsObj.v1;
        tr.appendChild(tdV1);
        
        const tdV2 = document.createElement("td");
        tdV2.innerText = metricsObj.v2;
        tr.appendChild(tdV2);
        
        const tdDelta = document.createElement("td");
        const delta = metricsObj.delta;
        
        if (delta > 0) {
            tdDelta.className = "delta-lbl plus";
            tdDelta.innerText = `+${delta}`;
        } else if (delta < 0) {
            tdDelta.className = "delta-lbl minus";
            tdDelta.innerText = `${delta}`;
        } else {
            tdDelta.className = "delta-lbl neutral";
            tdDelta.innerText = "0";
        }
        
        tr.appendChild(tdDelta);
        tableBody.appendChild(tr);
    }

    // Approve all pending handler
    approveAllBtn.addEventListener("click", async () => {
        const version = audVersionSelect.value;
        if (!version) {
            alert("Please select a version first.");
            return;
        }
        if (!confirm("Are you sure you want to approve all pending conversations and add them to the dataset?")) {
            return;
        }
        
        approveAllBtn.disabled = true;
        const origHtml = approveAllBtn.innerHTML;
        approveAllBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';
        
        try {
            const res = await fetch("/api/approve-all-conversations", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ version })
            });
            const data = await res.json();
            if (data.error) {
                alert(`Error: ${data.error}`);
            } else {
                loadDatasetDetails(version);
                loadStatus();
            }
        } catch (err) {
            alert(`Failed to approve all: ${err}`);
        } finally {
            approveAllBtn.disabled = false;
            approveAllBtn.innerHTML = origHtml;
        }
    });

    // Clean slate handler
    cleanSlateBtn.addEventListener("click", async () => {
        if (!confirm("Are you sure you want to Clean Slate? This will wipe out all normalized/anonymized files, generated datasets, annotations, exclusions, and custom role assignments. Your raw inputs under raw/ will be preserved.")) {
            return;
        }
        
        cleanSlateBtn.disabled = true;
        const origHtml = cleanSlateBtn.innerHTML;
        cleanSlateBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Cleaning...';
        
        try {
            const res = await fetch("/api/clean-slate", {
                method: "POST"
            });
            const data = await res.json();
            if (data.error) {
                alert(`Error clearing: ${data.error}`);
            } else {
                alert("Clean Slate complete! All normalized logs and datasets wiped.");
                activeLanguage = "All";
                loadStatus();
                // Select first version or reload
                const version = audVersionSelect.value;
                if (version) {
                    loadDatasetDetails(version);
                } else {
                    // Hide metrics
                    auditorMetricsGrid.style.display = "none";
                    auditorVizContainer.style.display = "none";
                    auditorPreviewContainer.style.display = "none";
                    auditorPendingContainer.style.display = "none";
                    auditorRolesContainer.style.display = "none";
                    auditorExplorerLayout.style.display = "none";
                }
            }
        } catch (err) {
            alert(`Failed to clean slate: ${err}`);
        } finally {
            cleanSlateBtn.disabled = false;
            cleanSlateBtn.innerHTML = origHtml;
        }
    });

    async function approveLanguage(version, language, replaceWith = null) {
        try {
            showConsole(`Authorizing language "${language}"...`);
            const payload = { version, language };
            if (replaceWith) {
                payload.replace_with = replaceWith;
            }
            const res = await fetch("/api/approve-language", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.error) {
                showConsole(`Error approving language: ${data.error}`);
                alert(`Error: ${data.error}`);
            } else {
                if (replaceWith) {
                    showConsole(`Language "${language}" mapped to "${replaceWith}" and authorized!`);
                    alert(`Language "${language}" mapped to "${replaceWith}" successfully!`);
                } else {
                    showConsole(`Language "${language}" approved successfully! Dataset rebuilt.`);
                    alert(`Language "${language}" authorized!`);
                }
                loadDatasetDetails(version);
                loadStatus();
            }
        } catch (err) {
            showConsole(`Network error: ${err}`);
            alert(`Failed to approve language: ${err}`);
        }
    }

    function createFlaggedControls(lang, version) {
        const wrap = document.createElement("div");
        wrap.style.display = "inline-flex";
        wrap.style.alignItems = "center";
        wrap.style.gap = "6px";
        wrap.style.margin = "4px 8px 4px 0";
        wrap.style.flexWrap = "wrap";

        const allowBtn = document.createElement("button");
        allowBtn.className = "btn-approve";
        allowBtn.style.padding = "3px 8px";
        allowBtn.style.fontSize = "11px";
        allowBtn.innerHTML = `<i class="fa-solid fa-check"></i> Allow ${lang}`;
        allowBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            approveLanguage(version, lang);
        });
        wrap.appendChild(allowBtn);

        const mapSelect = document.createElement("select");
        mapSelect.className = "styled-select";
        mapSelect.style.padding = "2px 4px";
        mapSelect.style.fontSize = "11px";
        mapSelect.style.width = "auto";
        mapSelect.style.height = "auto";
        mapSelect.style.color = "var(--text-primary)";
        mapSelect.style.background = "var(--bg-primary)";
        mapSelect.style.border = "1px solid rgba(255, 255, 255, 0.1)";
        mapSelect.innerHTML = `
            <option value="">Re-classify to...</option>
            <option value="en - English">en - English</option>
            <option value="hi - Hindi">hi - Hindi</option>
            <option value="ta - Tamil">ta - Tamil</option>
            <option value="gu - Gujarati">gu - Gujarati</option>
            <option value="mr - Marathi">mr - Marathi</option>
            <option value="te - Telugu">te - Telugu</option>
            <option value="kn - Kannada">kn - Kannada</option>
            <option value="bn - Bengali">bn - Bengali</option>
            <option value="ml - Malayalam">ml - Malayalam</option>
            <option value="no lang found - No Language Found">no lang found - No Language Found</option>
            <option value="CUSTOM">Custom...</option>
        `;
        
        const mapBtn = document.createElement("button");
        mapBtn.className = "btn-approve";
        mapBtn.style.padding = "3px 6px";
        mapBtn.style.fontSize = "11px";
        mapBtn.innerText = "Map";
        mapBtn.disabled = true;

        mapSelect.addEventListener("change", () => {
            mapBtn.disabled = !mapSelect.value;
        });

        mapBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            let targetLang = mapSelect.value;
            if (targetLang === "CUSTOM") {
                const custom = prompt("Enter language in 'code - Proper Name' format (e.g. es - Spanish):");
                if (!custom || !custom.includes(" - ")) {
                    alert("Invalid format! Use 'code - Name'.");
                    return;
                }
                targetLang = custom;
            }
            approveLanguage(version, lang, targetLang);
        });

        wrap.appendChild(mapSelect);
        wrap.appendChild(mapBtn);
        return wrap;
    }

    // Trigger initial loading
    loadStatus();
});
