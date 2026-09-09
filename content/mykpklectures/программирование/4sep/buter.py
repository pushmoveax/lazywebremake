components=[]
print("Вы хотите приготовить бутерброд? Вводите желаемые компоненты пока не надоест!")
while True:
    component=input("Введите желаемую начинку. Чтобы закончить сэндвич, напишите стоп:")
    if component == "стоп":
        break

    components.append(component)

print("Ваш сэндвич:")

for component in components:
    print(component)