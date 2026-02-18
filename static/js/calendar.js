/**
 * FullCalendar initialization for Bentley Boat Club.
 * Called from calendar.html with the API URL and reserve URL template.
 */
function initCalendar(apiUrl, reserveUrlTemplate) {
  const calEl = document.getElementById('calendar');
  if (!calEl) return;

  const calendar = new FullCalendar.Calendar(calEl, {
    initialView: window.innerWidth < 600 ? 'listMonth' : 'dayGridMonth',
    headerToolbar: {
      left:   'prev,next today',
      center: 'title',
      right:  'dayGridMonth,listMonth',
    },
    buttonText: {
      today:     'Today',
      month:     'Month',
      listMonth: 'List',
    },
    height: 'auto',
    fixedWeekCount: false,

    // Load reservations from the server for the visible range
    events: {
      url:         apiUrl,
      method:      'GET',
      extraParams: {},
      failure:     () => console.warn('Failed to load reservations'),
    },

    // Tap an empty day → go to reserve page for that date
    dateClick: function(info) {
      window.location.href = reserveUrlTemplate.replace('DATE', info.dateStr);
    },

    // Events already have url set; FullCalendar follows them on click
    eventClick: function(info) {
      info.jsEvent.preventDefault();
      if (info.event.url) {
        window.location.href = info.event.url;
      }
    },

    // Style tweaks
    eventDisplay: 'block',
    dayMaxEvents: 2,
  });

  calendar.render();
}
