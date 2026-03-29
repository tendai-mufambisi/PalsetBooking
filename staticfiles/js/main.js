(function() {
  "use strict";

  // Search-specific variables - isolated scope
  let mobileSearch = null;

  /**
   * Fast Preloader - Minimal delay
   */
  function initFastPreloader() {
    const preloader = document.querySelector('#preloader');
    if (!preloader) return;

    // Remove preloader as soon as page is interactive, not fully loaded
    const removePreloader = () => {
      // Check if preloader still exists (in case of fast navigation)
      if (!preloader.parentNode) return;
      
      preloader.style.opacity = '0';
      preloader.style.visibility = 'hidden';
      preloader.style.transition = 'all 0.3s ease';
      
      setTimeout(() => {
        if (preloader.parentNode) {
          preloader.parentNode.removeChild(preloader);
        }
      }, 300);
    };

    // Try to remove preloader quickly - but don't interfere with page navigation
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
      setTimeout(removePreloader, 500); // Small delay for better UX
    } else {
      // Remove when DOM is ready, don't wait for all resources
      document.addEventListener('DOMContentLoaded', () => {
        setTimeout(removePreloader, 500);
      });
      
      // Fallback: remove after max 1.5 seconds regardless
      setTimeout(removePreloader, 1500);
    }
  }

  /**
   * Ensure all page content is visible and properly styled
   */
  function ensureContentVisibility() {
    // Make sure body is visible and has proper styling
    const body = document.body;
    if (body) {
      body.style.visibility = 'visible';
      body.style.opacity = '1';
    }

    // Ensure all main content sections are visible
    const mainSections = document.querySelectorAll('main, section, .container, .content, [class*="section"]');
    mainSections.forEach(section => {
      section.style.visibility = 'visible';
      section.style.opacity = '1';
    });

    // Ensure images are loaded and visible
    const images = document.querySelectorAll('img');
    images.forEach(img => {
      img.style.visibility = 'visible';
      img.style.opacity = '1';
    });

    console.log('Page content visibility ensured');
  }

  /**
   * Initialize basic page functionality that works on ALL pages
   */
  function initBasicPageFunctionality() {
    // Ensure content is visible
    ensureContentVisibility();

    // Initialize any basic animations or interactions that should work everywhere
    initBasicAnimations();
    
    // Initialize any common UI components
    initCommonUI();
  }

  /**
   * Initialize basic animations that work on all pages
   */
  function initBasicAnimations() {
    // Add basic fade-in animation for all content
    const style = document.createElement('style');
    style.textContent = `
      .content-fade-in {
        animation: fadeIn 0.6s ease-in-out;
      }
      @keyframes fadeIn {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
      }
    `;
    document.head.appendChild(style);

    // Add fade-in class to main content areas
    setTimeout(() => {
      const mainContent = document.querySelector('main') || document.querySelector('.content') || document.body;
      if (mainContent) {
        mainContent.classList.add('content-fade-in');
      }
    }, 100);
  }

  /**
   * Initialize common UI components that work on all pages
   */
  function initCommonUI() {
    // Initialize any common buttons, links, or UI elements
    const buttons = document.querySelectorAll('button, .btn, a[href="#"]');
    buttons.forEach(btn => {
      btn.addEventListener('click', function(e) {
        if (this.getAttribute('href') === '#') {
          e.preventDefault();
        }
      });
    });

    // Ensure all links work properly
    const links = document.querySelectorAll('a[href]:not([href="#"])');
    links.forEach(link => {
      link.addEventListener('click', function(e) {
        // Allow normal navigation
        console.log('Navigating to:', this.href);
      });
    });
  }

  /**
   * Independent Mobile Search Functionality
   * This code only handles search and won't interfere with tours
   */
  function initMobileSearch() {
    // Only initialize if search elements exist AND we're on a page with tours
    const searchTrigger = document.querySelector('.search-trigger');
    const searchModal = document.getElementById('searchModal');
    const toursSection = document.getElementById('tours') || 
                        document.querySelector('.et-tours-section') ||
                        document.querySelector('.tours-section');
    
    // If no tours section exists, don't initialize search (we're probably on a different page)
    if (!toursSection) {
      console.log('Not a tours page - search disabled');
      return;
    }
    
    if (!searchTrigger || !searchModal) {
      console.log('Search elements not found - search disabled');
      return;
    }

    // Prevent duplicate initialization
    if (window.mobileSearchInitialized) return;
    window.mobileSearchInitialized = true;

    console.log('Initializing mobile search on tours page');

    searchTrigger.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      openMobileSearch();
    });

    function openMobileSearch() {
      if (!mobileSearch) {
        mobileSearch = new MobileSearch();
        window.mobileSearch = mobileSearch; // Global reference for search only
      }
      mobileSearch.openSearch();
    }

    // Mobile Search Class - Completely Independent
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

        console.log('Mobile Search initialized');

        // Event Listeners - Isolated to search elements only
        const closeSearchBtn = this.modal.querySelector('.close-search');
        const clearSearchBtn = this.modal.querySelector('.clear-search');
        
        if (closeSearchBtn) {
          closeSearchBtn.addEventListener('click', () => this.closeSearch());
        }
        
        if (clearSearchBtn) {
          clearSearchBtn.addEventListener('click', () => this.clearSearch());
        }
        
        // Search input handling
        this.searchInput.addEventListener('input', this.debounce((e) => {
          this.handleSearch(e.target.value);
        }, 300));
        
        // Mobile keyboard handling
        this.searchInput.addEventListener('focus', () => {
          this.showSuggestions();
          this.searchInput.setAttribute('inputmode', 'search');
        });
        
        // Search submission
        this.searchInput.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            this.handleSearchSubmit();
          }
        });

        // Close modal when clicking outside
        this.modal.addEventListener('click', (e) => {
          if (e.target === this.modal) this.closeSearch();
        });

        // Keyboard shortcuts - only for search
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

        // Search suggestions
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

      // Debounce utility - isolated to this class
      debounce(func, wait) {
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

      openSearch() {
        if (!this.modal) return;
        
        this.modal.classList.add('active');
        
        setTimeout(() => {
          this.modal.classList.add('animate-in');
          if (this.searchInput) {
            this.searchInput.focus();
            this.searchInput.setAttribute('inputmode', 'search');
          }
        }, 10);
        
        this.showSuggestions();
      }

      closeSearch() {
        if (!this.modal) return;
        
        this.modal.classList.remove('animate-in');
        
        setTimeout(() => {
          this.modal.classList.remove('active');
          this.clearSearch();
          if (this.searchInput) {
            this.searchInput.blur();
          }
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

      handleSearchSubmit() {
        const query = this.searchInput ? this.searchInput.value.trim() : '';
        if (query) {
          this.closeSearch();
          setTimeout(() => {
            this.processSearchAndNavigate(query);
          }, 350);
        } else {
          // If no query, just close search and allow normal scrolling
          this.closeSearch();
        }
      }

      processSearchAndNavigate(query) {
        // Check if we're still on a page with tours
        const toursSection = document.getElementById('tours') || 
                            document.querySelector('.et-tours-section') ||
                            document.querySelector('.tours-section');
        
        if (!toursSection) {
          console.log('Not on tours page - search navigation cancelled');
          return;
        }

        // Check if search returns any results
        const hasResults = this.checkSearchResults(query);
        
        if (!hasResults) {
          // Show "not available" message and show all tours
          this.showNotAvailableMessage(query);
          this.showAllTours();
        }
        
        // Navigate to tours section with minimal scroll
        this.navigateToToursSection(hasResults);
      }

      checkSearchResults(query) {
        if (!query.trim()) return true;
        
        const allTourCards = document.querySelectorAll('.et-tour-card');
        const filteredTours = Array.from(allTourCards).filter(tourCard => {
          const computedStyle = window.getComputedStyle(tourCard);
          return computedStyle.display !== 'none';
        });
        
        return filteredTours.length > 0;
      }

      showNotAvailableMessage(query) {
        // Create a temporary notification
        const notification = document.createElement('div');
        notification.className = 'search-notification';
        notification.innerHTML = `
          <div class="notification-content">
            <i class="bi bi-info-circle"></i>
            <span>"${query}" not found. Showing all available tours.</span>
          </div>
        `;
        
        document.body.appendChild(notification);
        
        // Remove notification after animation
        setTimeout(() => {
          if (notification.parentNode) {
            notification.parentNode.removeChild(notification);
          }
        }, 3000);
      }

      showAllTours() {
        // Safely interact with tours elements without conflicts
        const mainSearchInput = document.getElementById('et-search-input');
        if (mainSearchInput) {
          mainSearchInput.value = '';
          mainSearchInput.dispatchEvent(new Event('input', { bubbles: true }));
        }
        
        const filterSelect = document.getElementById('et-filter-select');
        if (filterSelect) {
          filterSelect.value = 'all';
          filterSelect.dispatchEvent(new Event('change', { bubbles: true }));
        }
        
        // Reset to first tab if needed
        const firstTab = document.querySelector('.et-tab');
        if (firstTab && !firstTab.classList.contains('active')) {
          firstTab.click();
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

        this.closeSearch();

        setTimeout(() => {
          // Check if we're still on a page with tours
          const toursSection = document.getElementById('tours') || 
                              document.querySelector('.et-tours-section') ||
                              document.querySelector('.tours-section');
          
          if (!toursSection) {
            console.log('Not on tours page - suggestion action cancelled');
            return;
          }

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

          if (target === 'tours') {
            this.navigateToToursSection(true);
          }
        }, 350);
      }

      applyCategoryFilter(category) {
        const filterSelect = document.getElementById('et-filter-select');
        if (filterSelect) {
          filterSelect.value = category;
          filterSelect.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }

      switchToTab(tabName) {
        const targetTab = document.querySelector(`.et-tab[data-tab="${tabName}"]`);
        if (targetTab) {
          targetTab.click();
        }
      }

      navigateToToursSection(hasResults) {
        const toursSection = document.getElementById('tours') || 
                            document.querySelector('.et-tours-section') ||
                            document.querySelector('.tours-section') ||
                            document.querySelector('.et-tours-grid')?.closest('section');
        
        if (toursSection && toursSection.isConnected) {
          const header = document.querySelector('#header');
          const headerHeight = header ? header.offsetHeight : 80;
          
          if (hasResults) {
            // For successful searches, scroll to top of tours section
            const yOffset = -headerHeight - 20;
            this.quickScrollTo(toursSection, yOffset);
          } else {
            // For no results, scroll minimally so user can see all tours
            const minimalOffset = -headerHeight + 50; // Show more content
            this.quickScrollTo(toursSection, minimalOffset);
          }

          // Brief visual feedback
          toursSection.style.animation = 'searchHighlightPulse 1.5s ease';
          setTimeout(() => {
            toursSection.style.animation = '';
          }, 1500);
        }
      }

      // Quick scroll function - minimal interruption
      quickScrollTo(element, offset = 0) {
        const targetY = element.getBoundingClientRect().top + window.pageYOffset + offset;
        
        // Use instant scroll for better UX - let user control scrolling after
        window.scrollTo({
          top: Math.max(0, targetY),
          behavior: 'smooth'
        });
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
        
        // Sync with main search input safely
        const mainSearchInput = document.getElementById('et-search-input');
        if (mainSearchInput && mainSearchInput.isConnected) {
          mainSearchInput.value = query;
          mainSearchInput.dispatchEvent(new Event('input', { bubbles: true }));
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
            <div class="suggestion-item" data-tour-id="${tourId}">
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

        // Add click handlers for tour results
        this.resultsContainer.querySelectorAll('.suggestion-item').forEach(item => {
          item.addEventListener('click', () => {
            const tourId = item.getAttribute('data-tour-id');
            this.navigateToTour(tourId);
          });
        });
      }

      navigateToTour(tourId) {
        this.closeSearch();
        
        setTimeout(() => {
          this.scrollToTour(tourId);
        }, 350);
      }

      scrollToTour(tourId) {
        const tourCard = document.querySelector(`.et-tour-card[data-tour-id="${tourId}"]`);
        if (tourCard && tourCard.isConnected) {
          const header = document.querySelector('#header');
          const headerHeight = header ? header.offsetHeight : 80;
          const yOffset = -headerHeight + 20; // Show more context around the card
          
          this.quickScrollTo(tourCard, yOffset);
          
          // Highlight effect
          tourCard.style.animation = 'searchHighlightPulse 1.5s ease';
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

    // Add search-specific styles
    this.addSearchStyles();
  }

  /**
   * Add search-specific styles that won't conflict
   */
  function addSearchStyles() {
    if (document.getElementById('search-only-styles')) return;
    
    const searchStyle = document.createElement('style');
    searchStyle.id = 'search-only-styles';
    searchStyle.textContent = `
      /* Search-specific animations */
      @keyframes searchHighlightPulse {
          0% { 
              box-shadow: 0 0 0 0 rgba(74, 108, 247, 0.3);
          }
          50% { 
              box-shadow: 0 0 0 10px rgba(74, 108, 247, 0);
          }
          100% { 
              box-shadow: 0 0 0 0 rgba(74, 108, 247, 0);
          }
      }

      @keyframes searchSlideUp {
          from {
              opacity: 0;
              transform: translateY(30px);
          }
          to {
              opacity: 1;
              transform: translateY(0);
          }
      }

      .search-modal.animate-in .search-modal-content {
          animation: searchSlideUp 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      }

      /* Fast preloader styles */
      #preloader {
        transition: all 0.3s ease !important;
      }

      /* Notification styles */
      .search-notification {
        position: fixed;
        top: 100px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(255, 77, 77, 0.95);
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        z-index: 10000;
        animation: notificationSlideIn 0.5s ease, notificationSlideOut 0.5s ease 2.5s forwards;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        max-width: 90%;
        width: auto;
      }
      .notification-content {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 14px;
        font-weight: 500;
      }
      .notification-content i {
        font-size: 16px;
      }
      @keyframes notificationSlideIn {
        from {
          opacity: 0;
          transform: translateX(-50%) translateY(-20px);
        }
        to {
          opacity: 1;
          transform: translateX(-50%) translateY(0);
        }
      }
      @keyframes notificationSlideOut {
        to {
          opacity: 0;
          transform: translateX(-50%) translateY(-20px);
        }
      }

      /* Search modal styles */
      .search-modal {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.8);
        z-index: 9999;
        display: none;
      }
      .search-modal.active {
        display: block;
      }
      .search-modal-content {
        background: white;
        margin: 2rem auto;
        max-width: 600px;
        border-radius: 12px;
        overflow: hidden;
        max-height: 80vh;
        overflow-y: auto;
      }

      /* Mobile input */
      #mobileSearch {
        font-size: 16px;
        -webkit-appearance: none;
        border-radius: 8px;
      }

      /* No results styling */
      .no-results {
        text-align: center;
        padding: 2rem;
        color: #6c757d;
      }
      .no-results i {
        font-size: 3rem;
        margin-bottom: 1rem;
        color: #dee2e6;
      }
      .no-results h3 {
        margin-bottom: 0.5rem;
        color: #495057;
      }
      .no-results p {
        color: #6c757d;
      }
    `;
    document.head.appendChild(searchStyle);
  }

  /**
   * Initialize everything when DOM is ready
   */
  function initAll() {
    console.log('Initializing page functionality...');
    
    // Initialize basic page functionality that works on ALL pages
    initBasicPageFunctionality();
    
    // Initialize fast preloader first
    initFastPreloader();
    
    // Initialize search functionality only if we're on a tours page
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => {
        initMobileSearch();
        console.log('DOM fully loaded - all content should be visible');
      });
    } else {
      initMobileSearch();
      console.log('DOM already ready - all content should be visible');
    }
  }

  // Start initialization
  initAll();

})();

const featuredToursSwiper = new Swiper('.featured-tours-slider', {
  slidesPerView: 'auto',
  centeredSlides: true,
  spaceBetween: 20,
  loop: true,
  pagination: {
    el: '.swiper-pagination',
    clickable: true,
  },
  breakpoints: {
    640: {
      spaceBetween: 30,
    },
    1024: {
      spaceBetween: 40,
    },
  },
});