(function() {
    "use strict";

    // Global variables
    let mobileSearch = null;
    let etCurrentTab = 'harare';
    let etCurrentTours = [];

    /**
     * Apply .scrolled class to the body as the page is scrolled down
     */
    function toggleScrolled() {
        const selectBody = document.querySelector('body');
        const selectHeader = document.querySelector('#header');
        if (!selectHeader) return;
        
        const isSticky = selectHeader.classList.contains('scroll-up-sticky') || 
                        selectHeader.classList.contains('sticky-top') || 
                        selectHeader.classList.contains('fixed-top');
        
        if (!isSticky) return;
        
        if (window.scrollY > 100) {
            selectBody.classList.add('scrolled');
        } else {
            selectBody.classList.remove('scrolled');
        }
    }

    document.addEventListener('scroll', toggleScrolled);
    window.addEventListener('load', toggleScrolled);

    /**
     * Enhanced Mobile Nav Toggle - Unified Function
     */
    const mobileNavToggleBtn = document.querySelector('.mobile-nav-toggle');
    const mobileMenuTrigger = document.querySelector('.mobile-menu-trigger');

    function mobileNavToggle() {
        const body = document.querySelector('body');
        const navmenu = document.getElementById('navmenu');
        
        if (!body || !navmenu) return;
        
        body.classList.toggle('mobile-nav-active');
        navmenu.classList.toggle('mobile-nav-active');
        
        if (mobileNavToggleBtn) {
            mobileNavToggleBtn.classList.toggle('bi-list');
            mobileNavToggleBtn.classList.toggle('bi-x');
        }
        
        // Prevent body scroll when mobile nav is active
        if (body.classList.contains('mobile-nav-active')) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = '';
        }
    }

    // Mobile nav toggle button
    if (mobileNavToggleBtn) {
        mobileNavToggleBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            mobileNavToggle();
        });
    }

    // Mobile bottom nav menu trigger
    if (mobileMenuTrigger) {
        mobileMenuTrigger.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            mobileNavToggle();
        });
    }

    /**
     * Hide mobile nav on same-page/hash links
     */
    function initNavMenuLinks() {
        const navmenuLinks = document.querySelectorAll('#navmenu a');
        navmenuLinks.forEach(navmenu => {
            navmenu.addEventListener('click', () => {
                if (document.querySelector('.mobile-nav-active')) {
                    mobileNavToggle();
                }
            });
        });
    }

    /**
     * Enhanced Toggle mobile nav dropdowns
     */
    function initMobileDropdowns() {
        // For toggle-dropdown elements
        document.querySelectorAll('.navmenu .toggle-dropdown').forEach(navmenu => {
            navmenu.addEventListener('click', function(e) {
                if (window.innerWidth < 1200) {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    const parent = this.parentNode;
                    const dropdown = parent.nextElementSibling;
                    
                    if (!dropdown) return;
                    
                    // Close other dropdowns
                    document.querySelectorAll('.navmenu .dropdown-active').forEach(active => {
                        if (active !== dropdown) {
                            active.classList.remove('dropdown-active');
                            const prevElement = active.previousElementSibling;
                            if (prevElement) prevElement.classList.remove('active');
                        }
                    });
                    
                    // Toggle current dropdown
                    parent.classList.toggle('active');
                    dropdown.classList.toggle('dropdown-active');
                }
            });
        });

        // For dropdown menu items
        document.querySelectorAll('.navmenu .dropdown > a').forEach(toggle => {
            toggle.addEventListener('click', function(e) {
                if (window.innerWidth < 1200) {
                    e.preventDefault();
                    const dropdown = this.parentElement;
                    const dropdownMenu = this.nextElementSibling;
                    
                    if (dropdownMenu && dropdownMenu.tagName === 'UL') {
                        // Close other dropdowns
                        document.querySelectorAll('.navmenu .dropdown ul.dropdown-active').forEach(active => {
                            if (active !== dropdownMenu) {
                                active.classList.remove('dropdown-active');
                                const prevElement = active.previousElementSibling;
                                if (prevElement) prevElement.classList.remove('active');
                            }
                        });
                        
                        // Toggle current dropdown
                        dropdownMenu.classList.toggle('dropdown-active');
                        dropdown.classList.toggle('active');
                    }
                }
            });
        });
    }

    /**
     * Close mobile menu when clicking outside
     */
    function initOutsideClickHandler() {
        document.addEventListener('click', function(event) {
            const body = document.body;
            const navmenu = document.getElementById('navmenu');
            
            if (!body.classList.contains('mobile-nav-active')) return;
            
            const clickedInsideNav = navmenu && navmenu.contains(event.target);
            const clickedMobileToggle = mobileNavToggleBtn && mobileNavToggleBtn.contains(event.target);
            const clickedBottomNavTrigger = mobileMenuTrigger && mobileMenuTrigger.contains(event.target);
            
            if (!clickedInsideNav && !clickedMobileToggle && !clickedBottomNavTrigger) {
                mobileNavToggle();
            }
        });
    }

    /**
     * Handle mobile bottom nav items
     */
    function initBottomNav() {
        const bottomNavItems = document.querySelectorAll('.mobile-bottom-nav .mobile-nav-item:not(.mobile-menu-trigger)');
        
        bottomNavItems.forEach(item => {
            item.addEventListener('click', function(e) {
                if (this.getAttribute('href') === '#') {
                    e.preventDefault();
                }
                
                // Update active state
                document.querySelectorAll('.mobile-bottom-nav .mobile-nav-item').forEach(navItem => {
                    navItem.classList.remove('active');
                });
                this.classList.add('active');
                
                // Close mobile menu if open
                if (document.body.classList.contains('mobile-nav-active')) {
                    mobileNavToggle();
                }
            });
        });

        // Add search functionality to bottom nav
        const searchBottomNav = document.querySelector('.mobile-bottom-nav .search-trigger');
        if (searchBottomNav) {
            searchBottomNav.addEventListener('click', function(e) {
                e.preventDefault();
                openMobileSearch();
            });
        }
    }

    /**
     * Tours Functionality - UPDATED FOR HTML-BASED TOURS
     */
    function initTours() {
        const etTabs = document.querySelectorAll('.et-tab');
        const etSearchInput = document.getElementById('et-search-input');
        const etFilterSelect = document.getElementById('et-filter-select');
        const etToursContainer = document.getElementById('et-tours-container');
        const allTourCards = document.querySelectorAll('.et-tour-card');

        // Set initial state
        etCurrentTours = Array.from(allTourCards).filter(card => card.dataset.tab === etCurrentTab);
        etRenderTours(etCurrentTours);

        // Initialize event listeners if elements exist
        if (etTabs.length > 0 && etToursContainer) {
            etSetupEventListeners();
        }

        function etSetupEventListeners() {
            // Tab switching
            etTabs.forEach(tab => {
                tab.addEventListener('click', () => {
                    etTabs.forEach(t => t.classList.remove('active'));
                    tab.classList.add('active');
                    etCurrentTab = tab.getAttribute('data-tab') || 'harare';
                    
                    // Filter tours by tab
                    etCurrentTours = Array.from(allTourCards).filter(card => card.dataset.tab === etCurrentTab);
                    etRenderTours(etCurrentTours);
                    
                    // Update mobile search results when tab changes
                    if (window.mobileSearch) {
                        const mobileSearchInput = document.getElementById('mobileSearch');
                        if (mobileSearchInput && mobileSearchInput.value) {
                            window.mobileSearch.handleSearch(mobileSearchInput.value);
                        }
                    }
                });
            });

            // Search functionality
            if (etSearchInput) {
                etSearchInput.addEventListener('input', debounce(() => {
                    etFilterTours();
                    
                    // Sync with mobile search
                    if (window.mobileSearch) {
                        const mobileSearchInput = document.getElementById('mobileSearch');
                        if (mobileSearchInput) {
                            mobileSearchInput.value = etSearchInput.value;
                        }
                        window.mobileSearch.displaySearchResults(etSearchInput.value);
                    }
                }, 300));
            }

            // Filter functionality
            if (etFilterSelect) {
                etFilterSelect.addEventListener('change', () => {
                    etFilterTours();
                    
                    // Update mobile search results when filter changes
                    if (window.mobileSearch) {
                        const mobileSearchInput = document.getElementById('mobileSearch');
                        if (mobileSearchInput && mobileSearchInput.value) {
                            window.mobileSearch.handleSearch(mobileSearchInput.value);
                        }
                    }
                });
            }
        }

        function etFilterTours() {
            const searchTerm = etSearchInput ? etSearchInput.value.toLowerCase() : '';
            const category = etFilterSelect ? etFilterSelect.value : 'all';

            const filteredTours = Array.from(allTourCards).filter(card => {
                const matchesTab = card.dataset.tab === etCurrentTab;
                const matchesSearch = card.dataset.tourName.toLowerCase().includes(searchTerm) || 
                                    card.querySelector('.et-tour-description').textContent.toLowerCase().includes(searchTerm) ||
                                    card.dataset.tourLocation.toLowerCase().includes(searchTerm);
                const matchesCategory = category === 'all' || card.dataset.tourCategory === category;
                
                return matchesTab && matchesSearch && matchesCategory;
            });

            etRenderTours(filteredTours);
        }

        function etRenderTours(tours) {
            const etToursContainer = document.getElementById('et-tours-container');
            if (!etToursContainer) return;

            // First, hide all tour cards
            allTourCards.forEach(card => {
                card.style.display = 'none';
            });

            if (!tours || tours.length === 0) {
                // Show no results message
                let noResults = etToursContainer.querySelector('.et-no-results');
                if (!noResults) {
                    noResults = document.createElement('div');
                    noResults.className = 'et-no-results';
                    noResults.innerHTML = `
                        <i class="bi bi-search"></i>
                        <h3>No tours found</h3>
                        <p>Try adjusting your search or filter criteria</p>
                    `;
                    etToursContainer.appendChild(noResults);
                }
                noResults.style.display = 'block';
                return;
            }

            // Hide no results message if it exists
            const noResults = etToursContainer.querySelector('.et-no-results');
            if (noResults) {
                noResults.style.display = 'none';
            }

            // Show filtered tours
            tours.forEach(tour => {
                tour.style.display = 'block';
            });

            // Re-initialize AOS for new visible elements
            if (typeof AOS !== 'undefined') {
                AOS.refresh();
            }
        }
    }

    /**
     * Utility function for debouncing
     */
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    /**
     * Preloader
     */
    function initPreloader() {
        const preloader = document.querySelector('#preloader');
        if (preloader) {
            window.addEventListener('load', () => {
                // Add fade-out class
                preloader.classList.add('fade-out');
                
                // Remove after animation
                setTimeout(() => {
                    preloader.remove();
                }, 500);
            });
            
            // Fallback: remove preloader after 3 seconds
            setTimeout(() => {
                if (document.body.contains(preloader)) {
                    preloader.remove();
                }
            }, 3000);
        }
    }

    /**
     * Animation on scroll function and init
     */
    function aosInit() {
        if (typeof AOS !== 'undefined') {
            AOS.init({
                duration: 600,
                easing: 'ease-in-out',
                once: true,
                mirror: false,
                offset: 100
            });
        }
    }

    /**
     * Initiate Pure Counter
     */
    function initPureCounter() {
        if (typeof PureCounter !== 'undefined') {
            new PureCounter();
        }
    }

    /**
     * Init swiper sliders
     */
    function initSwiper() {
        if (typeof Swiper !== 'undefined') {
            document.querySelectorAll(".init-swiper").forEach(function(swiperElement) {
                let configElement = swiperElement.querySelector(".swiper-config");
                if (!configElement) return;
                
                let config = JSON.parse(configElement.innerHTML.trim());

                if (swiperElement.classList.contains("swiper-tab")) {
                    // Handle swiper tabs if function exists
                    if (typeof initSwiperWithCustomPagination === 'function') {
                        initSwiperWithCustomPagination(swiperElement, config);
                    } else {
                        new Swiper(swiperElement, config);
                    }
                } else {
                    new Swiper(swiperElement, config);
                }
            });
        }
    }

    /**
     * Initiate glightbox
     */
    function initGlightbox() {
        if (typeof GLightbox !== 'undefined') {
            const glightbox = GLightbox({
                selector: '.glightbox',
                touchNavigation: true,
                loop: true,
                autoplayVideos: true
            });
        }
    }

    /**
     * Init isotope layout and filters
     */
    function initIsotope() {
        if (typeof Isotope !== 'undefined' && typeof imagesLoaded !== 'undefined') {
            document.querySelectorAll('.isotope-layout').forEach(function(isotopeItem) {
                let layout = isotopeItem.getAttribute('data-layout') ?? 'masonry';
                let filter = isotopeItem.getAttribute('data-default-filter') ?? '*';
                let sort = isotopeItem.getAttribute('data-sort') ?? 'original-order';

                let initIsotope;
                const isotopeContainer = isotopeItem.querySelector('.isotope-container');
                if (!isotopeContainer) return;
                
                imagesLoaded(isotopeContainer, function() {
                    initIsotope = new Isotope(isotopeContainer, {
                        itemSelector: '.isotope-item',
                        layoutMode: layout,
                        filter: filter,
                        sortBy: sort
                    });
                });

                isotopeItem.querySelectorAll('.isotope-filters li').forEach(function(filters) {
                    filters.addEventListener('click', function() {
                        const activeFilter = isotopeItem.querySelector('.isotope-filters .filter-active');
                        if (activeFilter) {
                            activeFilter.classList.remove('filter-active');
                        }
                        this.classList.add('filter-active');
                        initIsotope.arrange({
                            filter: this.getAttribute('data-filter')
                        });
                        if (typeof aosInit === 'function') {
                            aosInit();
                        }
                    }, false);
                });
            });
        }
    }

    /**
     * Frequently Asked Questions Toggle
     */
    function initFAQ() {
        document.querySelectorAll('.faq-item h3, .faq-item .faq-toggle, .faq-item .faq-header').forEach((faqItem) => {
            faqItem.addEventListener('click', () => {
                faqItem.parentNode.classList.toggle('faq-active');
            });
        });
    }

    /**
     * Nav buttons functionality
     */
    function initNavButtons() {
        const buttons = document.querySelectorAll('.nav-btn');
        buttons.forEach(btn => {
            btn.addEventListener('click', () => {
                buttons.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            });
        });
    }

    /**
     * Mobile Search Functionality - UPDATED FOR HTML-BASED TOURS
     */
    function initMobileSearch() {
        const searchTrigger = document.querySelector('.search-trigger');
        
        if (searchTrigger) {
            searchTrigger.addEventListener('click', function(e) {
                e.preventDefault();
                openMobileSearch();
            });
        }

        function openMobileSearch() {
            if (!mobileSearch) {
                mobileSearch = new MobileSearch();
                window.mobileSearch = mobileSearch;
            }
            mobileSearch.openSearch();
        }

        // Enhanced Mobile Search Class with Tour Navigation
        class MobileSearch {
            constructor() {
                this.modal = document.getElementById('searchModal');
                this.searchInput = document.getElementById('mobileSearch');
                this.suggestionsContainer = document.getElementById('searchSuggestions');
                this.resultsContainer = document.getElementById('searchResults');
                this.init();
            }

            init() {
                if (!this.modal || !this.searchInput) return;

                // Event Listeners
                const closeSearchBtn = this.modal.querySelector('.close-search');
                const clearSearchBtn = this.modal.querySelector('.clear-search');
                
                if (closeSearchBtn) {
                    closeSearchBtn.addEventListener('click', () => this.closeSearch());
                }
                
                if (clearSearchBtn) {
                    clearSearchBtn.addEventListener('click', () => this.clearSearch());
                }
                
                this.searchInput.addEventListener('input', debounce((e) => {
                    this.handleSearch(e.target.value);
                }, 300));
                
                this.searchInput.addEventListener('focus', () => this.showSuggestions());
                
                // Close modal when clicking outside
                this.modal.addEventListener('click', (e) => {
                    if (e.target === this.modal) this.closeSearch();
                });

                // Keyboard shortcuts
                document.addEventListener('keydown', (e) => {
                    if (e.key === 'Escape' && this.modal && this.modal.classList.contains('active')) {
                        this.closeSearch();
                    }
                    
                    // Ctrl+K or Cmd+K to open search
                    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                        e.preventDefault();
                        this.openSearch();
                    }
                });

                // Enhanced suggestions with navigation actions
                this.suggestions = [
                    { 
                        icon: 'bi-tree', 
                        title: 'Nature & Wildlife', 
                        description: 'Wildlife sanctuaries and natural sites', 
                        category: 'nature',
                        action: 'filter',
                        target: 'tours'
                    },
                    { 
                        icon: 'bi-building', 
                        title: 'Cultural & Historical', 
                        description: 'Historical landmarks and cultural sites', 
                        category: 'culture',
                        action: 'filter',
                        target: 'tours'
                    },
                    { 
                        icon: 'bi-compass', 
                        title: 'Adventure', 
                        description: 'Hiking and exploration tours', 
                        category: 'adventure',
                        action: 'filter',
                        target: 'tours'
                    },
                    { 
                        icon: 'bi-basket', 
                        title: 'Markets & Shopping', 
                        description: 'Local markets and shopping experiences', 
                        category: 'market',
                        action: 'filter',
                        target: 'tours'
                    },
                    { 
                        icon: 'bi-geo-alt', 
                        title: 'Harare Tours', 
                        description: 'Explore attractions in Harare', 
                        tab: 'harare',
                        action: 'switchTab',
                        target: 'tours'
                    },
                    { 
                        icon: 'bi-map', 
                        title: 'Zimbabwe Tours', 
                        description: 'Discover destinations across Zimbabwe', 
                        tab: 'zimbabwe',
                        action: 'switchTab',
                        target: 'tours'
                    },
                    { 
                        icon: 'bi-binoculars', 
                        title: 'View All Tours', 
                        description: 'Browse all available tour options', 
                        action: 'showAll',
                        target: 'tours'
                    }
                ];
            }

            openSearch() {
                if (!this.modal) return;
                
                this.modal.classList.add('active');
                document.body.style.overflow = 'hidden';
                
                setTimeout(() => {
                    this.modal.classList.add('animate-in');
                    if (this.searchInput) {
                        this.searchInput.focus();
                    }
                }, 10);
                
                this.showSuggestions();
            }

            closeSearch() {
                if (!this.modal) return;
                
                this.modal.classList.remove('animate-in');
                document.body.style.overflow = '';
                
                setTimeout(() => {
                    this.modal.classList.remove('active');
                    this.clearSearch();
                }, 300);
            }

            clearSearch() {
                if (this.searchInput) {
                    this.searchInput.value = '';
                }
                this.showSuggestions();
                if (this.searchInput) {
                    this.searchInput.focus();
                }
            }

            showAllTours() {
                // Clear main search input
                const mainSearchInput = document.getElementById('et-search-input');
                if (mainSearchInput) {
                    mainSearchInput.value = '';
                    const event = new Event('input');
                    mainSearchInput.dispatchEvent(event);
                }
                
                // Reset filter select
                const filterSelect = document.getElementById('et-filter-select');
                if (filterSelect) {
                    filterSelect.value = 'all';
                    const changeEvent = new Event('change');
                    filterSelect.dispatchEvent(changeEvent);
                }
            }

            showSuggestions() {
                if (!this.suggestionsContainer) return;
                
                const html = this.suggestions.map(suggestion => `
                    <div class="suggestion-item" 
                         data-action="${suggestion.action}"
                         data-category="${suggestion.category || ''}"
                         data-tab="${suggestion.tab || ''}"
                         data-target="${suggestion.target || ''}">
                        <i class="bi ${suggestion.icon}"></i>
                        <div class="suggestion-text">
                            <h4>${suggestion.title}</h4>
                            <p>${suggestion.description}</p>
                        </div>
                        <i class="bi bi-chevron-right"></i>
                    </div>
                `).join('');
                
                this.suggestionsContainer.innerHTML = html;
                if (this.resultsContainer) {
                    this.resultsContainer.innerHTML = '';
                }
                
                // Add click handlers for suggestions
                this.suggestionsContainer.querySelectorAll('.suggestion-item').forEach(item => {
                    item.addEventListener('click', () => {
                        this.handleSuggestionClick(item);
                    });
                });
            }

            handleSuggestionClick(suggestionItem) {
                const action = suggestionItem.dataset.action;
                const category = suggestionItem.dataset.category;
                const tab = suggestionItem.dataset.tab;
                const target = suggestionItem.dataset.target;

                // Close search modal first
                this.closeSearch();

                // Execute action after a short delay to allow modal to close
                setTimeout(() => {
                    switch (action) {
                        case 'filter':
                            this.applyCategoryFilter(category);
                            break;
                        
                        case 'switchTab':
                            this.switchToTab(tab);
                            break;
                        
                        case 'showAll':
                            this.showAllTours();
                            break;
                    }

                    // Navigate to tours section for all actions
                    if (target === 'tours') {
                        this.navigateToToursSection();
                    }
                }, 350);
            }

            applyCategoryFilter(category) {
                const filterSelect = document.getElementById('et-filter-select');
                if (filterSelect) {
                    filterSelect.value = category;
                    const changeEvent = new Event('change');
                    filterSelect.dispatchEvent(changeEvent);
                }
            }

            switchToTab(tabName) {
                const targetTab = document.querySelector(`.et-tab[data-tab="${tabName}"]`);
                if (targetTab) {
                    targetTab.click();
                }
            }

            navigateToToursSection() {
                // Try multiple selectors to find the tours section
                const toursSection = document.getElementById('easy-transit-tours') || 
                                    document.getElementById('tours') || 
                                    document.querySelector('.et-tours-section') ||
                                    document.querySelector('.tours-section') ||
                                    document.querySelector('.et-tours-grid')?.closest('section') ||
                                    document.querySelector('[data-tours-section]');
                
                if (toursSection) {
                    const header = document.querySelector('#header');
                    const headerHeight = header ? header.offsetHeight : 80;
                    const yOffset = -headerHeight;
                    const y = toursSection.getBoundingClientRect().top + window.pageYOffset + yOffset;
                    
                    window.scrollTo({
                        top: Math.max(0, y),
                        behavior: 'smooth'
                    });

                    // Add visual feedback
                    toursSection.style.animation = 'highlightPulse 2s ease';
                    setTimeout(() => {
                        toursSection.style.animation = '';
                    }, 2000);
                } else {
                    // Fallback: scroll to top of tours grid
                    const toursGrid = document.querySelector('.et-tours-grid');
                    if (toursGrid) {
                        const header = document.querySelector('#header');
                        const headerHeight = header ? header.offsetHeight : 80;
                        const yOffset = -headerHeight;
                        const y = toursGrid.getBoundingClientRect().top + window.pageYOffset + yOffset;
                        
                        window.scrollTo({
                            top: Math.max(0, y),
                            behavior: 'smooth'
                        });
                    }
                }
            }

            handleSearch(query) {
                if (!query.trim()) {
                    this.showSuggestions();
                    return;
                }
                this.filterTours(query);
            }

            filterTours(searchQuery) {
                const query = searchQuery.toLowerCase().trim();
                
                // Sync with main search input
                const mainSearchInput = document.getElementById('et-search-input');
                if (mainSearchInput) {
                    mainSearchInput.value = query;
                    const event = new Event('input');
                    mainSearchInput.dispatchEvent(event);
                }
                
                this.displaySearchResults(query);
            }

            displaySearchResults(query) {
                if (!this.resultsContainer) return;

                const allTourCards = document.querySelectorAll('.et-tour-card');
                const filteredTours = Array.from(allTourCards).filter(tourCard => {
                    const computedStyle = window.getComputedStyle(tourCard);
                    return computedStyle.display !== 'none';
                });
                
                if (filteredTours.length === 0) {
                    this.resultsContainer.innerHTML = `
                        <div class="no-results">
                            <i class="bi bi-search"></i>
                            <h3>No tours found</h3>
                            <p>No results for "${query}". Try different keywords.</p>
                        </div>
                    `;
                    if (this.suggestionsContainer) {
                        this.suggestionsContainer.innerHTML = '';
                    }
                    return;
                }

                const html = filteredTours.map(tourCard => {
                    const tourId = tourCard.getAttribute('data-tour-id');
                    const tourName = tourCard.getAttribute('data-tour-name');
                    const tourLocation = tourCard.getAttribute('data-tour-location');
                    const tourCategory = tourCard.getAttribute('data-tour-category');
                    
                    return `
                        <div class="suggestion-item" onclick="window.mobileSearch.navigateToTour(${tourId})">
                            <i class="bi ${this.getCategoryIcon(tourCategory)}"></i>
                            <div class="suggestion-text">
                                <h4>${tourName}</h4>
                                <p>${tourLocation} • ${this.getCategoryName(tourCategory)}</p>
                            </div>
                            <i class="bi bi-chevron-right"></i>
                        </div>
                    `;
                }).join('');

                this.resultsContainer.innerHTML = html;
                if (this.suggestionsContainer) {
                    this.suggestionsContainer.innerHTML = '';
                }
            }

            navigateToTour(tourId) {
                this.closeSearch();
                
                setTimeout(() => {
                    this.scrollToTour(tourId);
                }, 350);
            }

            scrollToTour(tourId) {
                const tourCard = document.querySelector(`.et-tour-card[data-tour-id="${tourId}"]`);
                if (tourCard) {
                    const header = document.querySelector('#header');
                    const headerHeight = header ? header.offsetHeight : 80;
                    const yOffset = -headerHeight;
                    const y = tourCard.getBoundingClientRect().top + window.pageYOffset + yOffset;
                    
                    window.scrollTo({
                        top: Math.max(0, y),
                        behavior: 'smooth'
                    });
                    
                    // Add highlight effect
                    tourCard.style.animation = 'highlightPulse 1.5s ease';
                    setTimeout(() => {
                        tourCard.style.animation = '';
                    }, 1500);
                }
            }

            getCategoryName(category) {
                const categoryNames = {
                    'nature': 'Nature & Wildlife',
                    'culture': 'Cultural & Historical',
                    'adventure': 'Adventure',
                    'market': 'Markets & Shopping'
                };
                return categoryNames[category] || category;
            }

            getCategoryIcon(category) {
                const categoryIcons = {
                    'nature': 'bi-tree',
                    'culture': 'bi-building',
                    'adventure': 'bi-compass',
                    'market': 'bi-basket'
                };
                return categoryIcons[category] || 'bi-geo-alt';
            }
        }
    }

    /**
     * Handle window resize - reset mobile states on desktop
     */
    function initResizeHandler() {
        let resizeTimeout;
        window.addEventListener('resize', function() {
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(function() {
                if (window.innerWidth >= 1200) {
                    const body = document.body;
                    const navmenu = document.getElementById('navmenu');
                    
                    // Reset mobile states when switching to desktop
                    body.classList.remove('mobile-nav-active');
                    if (navmenu) {
                        navmenu.classList.remove('mobile-nav-active');
                    }
                    
                    // Close all dropdowns
                    document.querySelectorAll('.navmenu .dropdown-active').forEach(dropdown => {
                        dropdown.classList.remove('dropdown-active');
                    });
                    
                    document.querySelectorAll('.navmenu .dropdown.active').forEach(dropdown => {
                        dropdown.classList.remove('active');
                    });
                    
                    // Reset mobile nav toggle icon
                    if (mobileNavToggleBtn) {
                        mobileNavToggleBtn.classList.add('bi-list');
                        mobileNavToggleBtn.classList.remove('bi-x');
                    }
                    
                    // Restore body scroll
                    document.body.style.overflow = '';
                }
            }, 250);
        });
    }

    /**
     * Update active nav button based on current page
     */
    function updateActiveNav() {
        const currentPage = window.location.pathname.split('/').pop() || 'index.html';
        const navButtons = document.querySelectorAll('.nav-btn');
        
        navButtons.forEach(btn => {
            btn.classList.remove('active');
            if (btn.getAttribute('href') === currentPage || 
                (currentPage === '' && btn.getAttribute('href') === 'index.html')) {
                btn.classList.add('active');
            }
        });
    }

    /**
     * Add highlight animation to CSS
     */
    function addHighlightStyles() {
        if (document.getElementById('highlight-styles')) return;
        
        const highlightStyle = document.createElement('style');
        highlightStyle.id = 'highlight-styles';
        highlightStyle.textContent = `
            @keyframes highlightPulse {
                0% { 
                    box-shadow: 0 0 0 0 rgba(102, 126, 234, 0.4);
                    transform: scale(1);
                }
                50% { 
                    box-shadow: 0 0 0 10px rgba(102, 126, 234, 0);
                    transform: scale(1.02);
                }
                100% { 
                    box-shadow: 0 0 0 0 rgba(102, 126, 234, 0);
                    transform: scale(1);
                }
            }

            @keyframes slideUp {
                from {
                    opacity: 0;
                    transform: translateY(30px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }

            .search-modal .search-modal-content {
                transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            }

            .search-modal.animate-in .search-modal-content {
                animation: slideUp 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            }

            .et-tour-card {
                transition: all 0.3s ease;
            }

            #preloader.fade-out {
                opacity: 0;
                visibility: hidden;
                transition: all 0.5s ease;
            }

            .suggestion-item {
                cursor: pointer;
                transition: all 0.2s ease;
            }

            .suggestion-item:hover {
                background-color: rgba(102, 126, 234, 0.1);
                transform: translateX(5px);
            }
        `;
        document.head.appendChild(highlightStyle);
    }

    /**
     * Initialize all components
     */
    function initAll() {
        // Add styles first
        addHighlightStyles();
        
        // Initialize core functionality
        initPreloader();
        initNavMenuLinks();
        initMobileDropdowns();
        initOutsideClickHandler();
        initBottomNav();
        initTours();
        initMobileSearch();
        initFAQ();
        initNavButtons();
        initResizeHandler();
        updateActiveNav();
        
        // Initialize third-party libraries after DOM is ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function() {
                aosInit();
                initPureCounter();
                initSwiper();
                initGlightbox();
                initIsotope();
            });
        } else {
            aosInit();
            initPureCounter();
            initSwiper();
            initGlightbox();
            initIsotope();
        }
    }

    // Start initialization
    initAll();

})();