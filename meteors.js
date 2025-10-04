// Fetch the JSON file
fetch("meteors.json")
  .then(response => response.json())
  .then(meteors => {
    const list = document.getElementById("meteorList");
    const details = document.getElementById("meteorDetails");

    meteors.forEach((meteor, index) => {
      const li = document.createElement("li");
      li.textContent = meteor.name;
      li.style.cursor = "pointer";

      li.addEventListener("click", () => {
        details.innerHTML = `
          <h2>${meteor.name}</h2>
          <p>Size: ${meteor.size}</p>
          <p>Speed: ${meteor.speed}</p>
          <p>Description: ${meteor.description}</p>
        `;
      });

      list.appendChild(li);
    });
  })
  .catch(err => console.error("Error loading meteors:", err));
