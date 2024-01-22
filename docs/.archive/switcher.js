function checkPathExists(url) {
    return new Promise((resolve, reject) => {
        var xhr = new XMLHttpRequest();
        xhr.open('HEAD', url, true);
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4) {
                if (xhr.status === 200) {
                    resolve(true);
                } else if (xhr.status === 404) {
                    resolve(false);
                } else {
                    reject(new Error(xhr.statusText));
                }
            }
        };
        xhr.onerror = function() {
            reject(new Error('Network Error'));
        };
        xhr.send();
    });
}

document.addEventListener('DOMContentLoaded', function() {
    // Get the specific dropdown menu by its ID
    var dropdownMenu = document.querySelector('#nav-menu-version').nextElementSibling;

    // Get all dropdown items within the specific dropdown menu
    var dropdownItems = dropdownMenu.querySelectorAll('.dropdown-item');

    // Get the current page's path
    var currentPagePath = window.location.pathname.split('/');
    console.log('current page path', currentPagePath);

    // Loop through each dropdown item
    for (var i = 0; i < dropdownItems.length; i++) {
      // Add click event listener to each item
      dropdownItems[i].addEventListener('click', function(event) {
        // Prevent default action
        event.preventDefault();

        // Get the clicked item's text
        var itemText = this.querySelector('.dropdown-text').textContent;
        var itemHref = this.getAttribute('href')

        // Loop through each dropdown item again to find a match in the current page's path
        for (var j = 0; j < dropdownItems.length; j++) {
          // Get the dropdown item's text
          var dropdownText = dropdownItems[j].querySelector('.dropdown-text').textContent;
          console.log('Dropdown item:', dropdownText);

          // Find the index of the dropdownText in the current page's path
          var index = currentPagePath.indexOf(dropdownText);

          // If the dropdownText is found in the current page's path
          if (index !== -1) {
            // Construct the new URL relative to the dropdownText and append the itemText
            addElements = currentPagePath.slice(index + 1, )
            relativePath = '../'.repeat(addElements.length)
            var newUrl = relativePath + itemText + '/' + addElements.join('/')
            console.log('Clicked item:', newUrl);

            // Redirect to the new URL
            checkPathExists(newUrl)
                .then(exists => {
                    if (exists) {
                        window.location.href = newUrl;
                    } else {
                        console.log('Path does not exist');
                    }
                })

            // Exit the loop
            break;
          }
        }
      });
    }
  });
