import numpy as np
import heapq
import csv

# --- KONFIGURACJA PROGRAMU ---
ADVANCED_LOGS = False

class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    GRAY = "\033[90m"

# --- PARAMETRY GŁÓWNE ---
SHIFT_CHANGE_TIME = 120.0  # Zmiana kasjera po 2 godzinach (w minutach)

class Simulation:
    def __init__(self, simulation_time):
        self.simulation_time = simulation_time
        # --- KOLEJKA ZDARZEŃ ---
        self.event_queue = [] 
        # --- STAN SYSTEMU ---
        self.queue = []
        self.current_time = 0.0
        self.next_customer_id = 1
        self.server_busy = False
        self.in_failure = False
        self.shift_effect_counter = 0 



        # --- STATYSTYKI ---
        self.served_customers = 0
        self.lost_customers = 0
        self.total_service_time = 0.0
        self.failure_count = 0
        self.total_failure_duration = 0.0
        self.unserved_due_to_timeout = 0


    # --- FUNKCJE GENERUJĄCE ZMIENNE LOSOWE ---
    def generate_arrival_time(self, mean=2.0, std=0.5, min_time=0.5):
        # Czas między przyjściami klientów
        return max(min_time, np.random.normal(loc=mean, scale=std))

    def generate_service_time(self, normal_mean=3.0, slow_mean_first=6.0, slow_mean_next=4.0, std=2, min_time=1.0, max_time=8.0):
        # Czas obsługi klienta - rozkład normalny z ograniczeniem
        if self.shift_effect_counter > 0:
            print(f"{Colors.MAGENTA}[{self.current_time:.2f}] Slower service due to cashier adjustment (client #{self.next_customer_id}){Colors.RESET}")
            if self.shift_effect_counter == 3:
                mean = slow_mean_first  # pierwszy klient po zmianie – mocne spowolnienie
            else:
                mean = slow_mean_next  # kolejni dwaj – lekkie spowolnienie
            self.shift_effect_counter -= 1
        else:
            mean = normal_mean

        base = np.random.normal(loc=mean, scale=std)
        return min(max(base, min_time), max_time)

    def generate_failure_time(self, shape=3.0, scale=120.0):
        # Czas do następnej awarii - rozkład gamma
        return np.random.gamma(shape=shape, scale=scale)

    def generate_failure_duration(self, alpha=2.0, beta=5.0, min_time=5.0, max_time=20.0):
        # Czas trwania awarii - rozkład beta przeskalowany do min_time-max_time
        base = np.random.beta(alpha, beta)
        return min_time + base * (max_time - min_time)

    # --- PLANOWANIE ZDARZEŃ ---
    def schedule_event(self, time, event_type, data=None):
        heapq.heappush(self.event_queue, (time, event_type, data))

    # --- OBSŁUGA KOLEJNEGO KLIENTA ---
    def process_next_client(self):
        if not self.server_busy and self.queue and not self.in_failure:
            client_id = self.queue.pop(0)
            service_time = self.generate_service_time()
            self.schedule_event(self.current_time + service_time, "service_end", (client_id, service_time))
            self.server_busy = True

    # --- OBSŁUGA ZDARZEŃ ---
    def handle_event(self, event_type, data):
        # Nowy klient przychodzi
        if event_type == "arrival":
            if self.in_failure:
                print(f"{Colors.RED}[{self.current_time:.2f}] Client {self.next_customer_id} wanted to arrive but there is failure{Colors.RESET}")
                self.lost_customers += 1
            else:
                self.queue.append(self.next_customer_id)
                print(f"[{self.current_time:.2f}] Client {self.next_customer_id} arrived")
                self.process_next_client()
            # Zaplanuj kolejne przyjście
            self.schedule_event(self.current_time + self.generate_arrival_time(), "arrival")
            if ADVANCED_LOGS: self.show_system_status()


        elif event_type == "service_end":
             # Klient został obsłużony (lub stracony, jeśli trwała awaria)
            if self.in_failure:
                self.lost_customers += 1
                print(f"{Colors.RED}[{self.current_time:.2f}] Client {data[0]} lost due to failure{Colors.RESET}")
            else:
                self.served_customers += 1
                self.total_service_time += data[1]
                print(f"{Colors.YELLOW}[{self.current_time:.2f}] Client {data[0]} served in {data[1]:.2f} minutes{Colors.RESET}")
            self.server_busy = False
            self.process_next_client()
            if ADVANCED_LOGS: self.show_system_status()


        elif event_type == "failure_start":
            # Rozpoczęcie awarii
            self.in_failure = True
            self.failure_count += 1
            print(f"{Colors.RED}[{self.current_time:.2f}] FAILURE started!{Colors.RESET}")

            # Klienci mogą się zniechęcić i odejść z kolejki w czasie awarii
            # 40% szans na odejście
            remaining_queue = []
            for client_id in self.queue:
                if np.random.rand() < 0.4:
                    print(f"[{self.current_time:.2f}] Client {client_id} left the queue during FAILURE")
                    self.lost_customers += 1
                else:
                    remaining_queue.append(client_id)
            self.queue = remaining_queue
            duration = self.generate_failure_duration()
            self.total_failure_duration += duration
            self.schedule_event(self.current_time + duration, "failure_end")
            if ADVANCED_LOGS: self.show_system_status()


        elif event_type == "failure_end":
            self.in_failure = False
            print(f"[{self.current_time:.2f}] FAILURE ended")
            self.process_next_client()
            # Zaplanuj kolejną awarię
            self.schedule_event(self.current_time + self.generate_failure_time(), "failure_start")
            if ADVANCED_LOGS: self.show_system_status()


        elif event_type == "shift_change":
            # Zmiana kasjera — oznacza początek spowolnienia
            self.shift_effect_counter = 3  # Pierwszych 3 klientów po zmianie kasjera będzie obsługiwanych wolniej
            print(f"{Colors.CYAN}[{self.current_time:.2f}] Shift change started{Colors.RESET}")
            self.schedule_event(self.current_time + SHIFT_CHANGE_TIME, "shift_change")  # Zaplanuj kolejną zmianę kasjera


    # --- GŁÓWNA PĘTLA SYMULACJI ---
    def run(self):
        # Startowe zdarzenia
        self.schedule_event(0.0, "arrival")
        self.schedule_event(self.generate_failure_time(), "failure_start")
        self.schedule_event(SHIFT_CHANGE_TIME, "shift_change")

        while self.event_queue and self.current_time <= self.simulation_time:
            time, event_type, data = heapq.heappop(self.event_queue)
            if time > self.simulation_time:
                break
            self.current_time = time
            if event_type == "arrival":
                self.next_customer_id += 1
            self.handle_event(event_type, data)

        # Statystyki końcowe
        avg_service_time = self.total_service_time / self.served_customers if self.served_customers > 0 else 0
        avg_failure_duration = self.total_failure_duration / self.failure_count if self.failure_count > 0 else 0

        # Klienci w kolejce i ewentualnie obsługiwany klient
        self.unserved_due_to_timeout = len(self.queue)
        if self.server_busy:
            self.unserved_due_to_timeout += 1  # klient w trakcie obsługi, ale nieukończonej


        # Wyświetlenie wyników w konsoli
        print("\n=== STATYSTYKI PO SYMULACJI ===")
        print(f"Liczba obsłużonych klientów: {self.served_customers}")
        print(f"Liczba utraconych klientów: {self.lost_customers}")
        print(f"Klienci w kolejce na koniec (nieobsłużeni): {self.unserved_due_to_timeout}")
        print(f"Liczba awarii: {self.failure_count}")
        print(f"Średni czas obsługi: {avg_service_time:.2f} minut")
        print(f"Średni czas trwania awarii: {avg_failure_duration:.2f} minut")



        return [self.served_customers, self.lost_customers, self.unserved_due_to_timeout, self.failure_count, avg_service_time, avg_failure_duration]
    
    def show_system_status(self):
        queue_visual = "🧍 x " + str(len(self.queue))
        server_status = "💼" if self.server_busy else "🟢"
        failure_status = "❌" if self.in_failure else ""
        shift_status = "🔄" if self.shift_effect_counter > 0 else ""
        print(f"    Queue: {queue_visual} | Server: {server_status} {failure_status}{shift_status}")



def run_multiple_simulations(num_simulations, simulation_time=480, output_file="simulation_results.csv"):
    headers = ["Simulation Number", "Served Customers", "Lost Customers", "Unserved at Timeout", "Failure Count", "Avg Service Time (min)", "Avg Failure Duration (min)"]
    with open(output_file, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(headers)

        for i in range(num_simulations):
            print(f"---- Running simulation {i+1}/{num_simulations} ----")
            sim = Simulation(simulation_time)
            results = sim.run()
            writer.writerow([i+1] + results)

# Uruchomienie symulacji
run_multiple_simulations(10)

