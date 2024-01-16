window.onload = function() {
    // Assuming you have a ul element in your HTML like this:
    // <ul id="myDropdown"></ul>

    // Fetch the JSON data
    fetch("http://localhost:8008/switcher.json")
      .then(response => response.json())
      .then(data => {
        console.log('Data loaded:', data); // Log the loaded data

        const dropdown = document.querySelector('#nav-menu-version').nextElementSibling;
        console.log('Dropdown element:', dropdown); // Log the dropdown element

        // Clear all existing dropdown items
        dropdown.innerHTML = '';

        data.forEach(item => {
            console.log('Adding item:', item); // Log the item being added

            // Create a new li element
            const li = document.createElement('li');

            // Create a new a element
            const a = document.createElement('a');
            a.className = 'dropdown-item';
            a.href = item.url; // Use the 'url' property as the href
            a.textContent = item.name; // Use the 'name' property as the text

            // Add the a element to the li
            li.appendChild(a);

            // Add the li to the dropdown
            dropdown.appendChild(li);
        });

        console.log('Dropdown after adding items:', dropdown); // Log the dropdown after adding items
        })
        .catch(error => console.error('Error:', error)); // Log any errors


}
