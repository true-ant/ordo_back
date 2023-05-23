
'use strict';

// let primaryColorVal = getComputedStyle(document.documentElement).getPropertyValue('--primary-bg-color').trim();
// myVarVal = localStorage.getItem("primaryColor") || localStorage.getItem("darkPrimary") || localStorage.getItem("transparentPrimary") || localStorage.getItem("transparentBgImgPrimary")  || primaryColorVal;

//Sales chart
function sales() {
  setTimeout(() => {
    var options = {
      series: [
        {
          name: 'REVENUE',
          data: JSON.parse(chart_data)
        },

      ],
      chart: {
        id: 'chartD',
        type: 'area',
        height: 345,
        zoom: {
          autoScaleYaxis: false
        }
      },

      colors: [myVarVal],
      dataLabels: {
        enabled: false
      },
      markers: {
        size: 0,
        style: 'hollow',
      },
      grid: {
        borderColor: '#f7f9fa',
      },
      xaxis: {
        type: 'datetime',
        min: new Date('01 Jan 2021').getTime(),
        axisBorder: {
          show: true,
          color: 'rgba(119, 119, 142, 0.05)',
          offsetX: 0,
          offsetY: 0,
        },
        axisTicks: {
          show: true,
          borderType: 'solid',
          color: 'rgba(119, 119, 142, 0.05)',
          width: 6,
          offsetX: 0,
          offsetY: 0
        },
        labels: {
          show: true,
          rotate: -90,
          style: {
            fontSize: '11px',
            fontFamily: 'Helvetica, Arial, sans-serif',
            fontWeight: 400,
            cssClass: 'apexcharts-xaxis-label',
          },
        },
        tooltip: {
          enabled: false
        }
      },
      yaxis: {
        title: {
          text: 'Growth',
          style: {
            color: '#adb5be',
            fontSize: '14px',
            fontFamily: 'poppins, sans-serif',
            fontWeight: 600,
            cssClass: 'apexcharts-yaxis-label',
          },
        },
        labels: {
          formatter: function (y) {
            return y.toFixed(0) + "";
          }
        }
      },
      tooltip: {
        x: {
          format: 'dd MMM yyyy'
        }
      },
      stroke: {
        show: true,
        curve: 'smooth',
        lineCap: 'butt',
        colors: undefined,
        width: 1,
        dashArray: 0,
      },
      fill: {
        type: 'gradient',
        gradient: {
          shadeIntensity: 1,
          opacityFrom: 0.75,
          opacityTo: 0.5,
          stops: [0, 200]
        }
      },

      legend: {
        position: "top",
        show: true
      }
    };
    document.getElementById('chartD').innerHTML = '';
    var chart = new ApexCharts(document.querySelector("#chartD"), options);
    chart.render();
  }, 300);
}

(function () {

  //______Data-Table
  $('#data-table').DataTable({
    language: {
      searchPlaceholder: 'Search...',
      sSearch: '',
      lengthMenu: '_MENU_',
    }
  });

  //______Select2 
  $('.select2').select2({
    minimumResultsForSearch: Infinity
  });

  //select2 with indicator
  function selectStatus(status) {
    if (!status.id) { return status.text; }
    var $status = $(
      '<span class="status-indicator projects">' + status.text + '</span>',
    );
    var $statusText = $status.text().split(" ").join("").toLowerCase();
    if ($statusText === "inprogress") {
      $status.addClass("in-progress");
    }
    else if ($statusText === "onhold") {
      $status.addClass("on-hold");
    }
    else if ($statusText === "completed") {
      $status.addClass("completed");
    }
    else {
      $status.addClass("empty");
    }
    return $status;
  };

  //upload
  $(".select2-status-search").select2({
    templateResult: selectStatus,
    templateSelection: selectStatus,
    escapeMarkup: function (s) { return s; }
  });

  var $file = $('#task-file-input'),
    $label = $file.next('label'),
    $labelText = $label.find('span'),
    $labelRemove = $('i.remove'),
    labelDefault = $labelText.text();

  // on file change
  $file.on('change', function (event) {
    var fileName = $file.val().split('\\').pop();
    if (fileName) {
      $labelText.text(fileName);
      $labelRemove.show();
    } else {
      $labelText.text(labelDefault);
      $labelRemove.hide();
    }
  });

  // Remove file   
  $labelRemove.on('click', function (event) {
    $file.val("");
    $labelText.text(labelDefault);
    $labelRemove.hide();
    console.log($file)
  });

})();

//todo task
const subTaskContainer = document.querySelector('.sub-list-container');
if (subTaskContainer) {

  const subTaskElement = document.querySelector('.sub-list-item');
  const addSubTaskBtn = document.querySelector('#addTask');
  const subTaskInput = document.querySelector('#subTaskInput');
  const errorNote = document.querySelector('#errorNote');
  const deleteAllTasks = document.querySelector('#deleteAllTasks');
  const completedAllBtn = document.querySelector('#completedAll');


  setTimeout(() => {
    setInterval(() => {
      const deleteBtn = document.querySelectorAll('.delete-main');
      for (let i = 0; i < deleteBtn.length; i++) {
        deleteBtn[i].addEventListener('click', deleteSubTask);
      }
    }, 10);
  }, 1);

  //delete task
  function deleteSubTask($e) {
    subTaskContainer.removeChild($e.target.parentElement);
  }

  //mark all as completed vice verca
  var count = 0;

  function markAllCompleted() {
    var allTasks = subTaskContainer.children;

    if (count % 2 != 0) {
      for (let i = 0; i < allTasks.length; i++) {

        allTasks[i].classList.remove('task-completed');
      }
    }
    else {
      for (let i = 0; i < allTasks.length; i++) {

        allTasks[i].classList.add('task-completed');
      }
    }
    count++;
  }

  //remove all tasks
  function removeAllTasks() {
    subTaskContainer.innerHTML = ' ';
  }

  //add new task
  var taskCopy = subTaskElement.cloneNode(true);
  function addNewTask() {
    errorNote.innerText = "";
    var newSubTask = taskCopy.cloneNode(true);
    newSubTask.classList.remove('task-completed')
    var newTaskText = subTaskInput.value;
    if (newTaskText.length !== 0) {
      subTaskContainer.appendChild(newSubTask);
      newSubTask.children[0].children[1].innerText = newTaskText;
      subTaskInput.value = "";
    }
    else {
      errorNote.innerText = "Please Enter Valid Input";
    }
  }

  //mark task as completed
  function taskCompleted($e) {
    var currentSubList = $e.target;
    var subListParent = currentSubList.parentElement.parentElement;

    if (subListParent.classList.contains('task-completed')) {
      subListParent.classList.remove('task-completed');
    }
    else {
      subListParent.classList.add('task-completed');
    }
  }

  completedAllBtn.addEventListener('click', markAllCompleted); // mark all completed
  deleteAllTasks.addEventListener('click', removeAllTasks);   //delete all tasks
  addSubTaskBtn.addEventListener('click', addNewTask);    //create new task
}