window.onload = function() {
    // Select corrent dropdown menu
    var dropdownMenu = document.querySelector('#nav-menu-select-version').nextElementSibling;

    // Get all dropdown items within the specific dropdown menu
    var dropdownItems = dropdownMenu.querySelectorAll('.dropdown-item');

    // Get the current page in chunks
    var currentPagePath = window.location.pathname.split('/');

    for (var i = 0; i < dropdownItems.length; i++) {
        // Get textcontent
        var textContent = dropdownItems[i].querySelector('.dropdown-text').textContent;

        // Get the index of the current version
        var index = currentPagePath.indexOf(textContent);

        if (index !== -1) {
            // Remove the active-item class from all items
            for (var j = 0; j < dropdownItems.length; j++) {
                dropdownItems[j].classList.remove('active-item');
            }

            dropdownItems[i].classList.add('active-item');
            break
        }
    }
}
